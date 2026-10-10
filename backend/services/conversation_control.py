"""Transactional pause and dispatch fencing. No function commits.

Callers must COMMIT a successful claim before transport. A committed claim is
already needs_review, so crashes/timeouts cannot cause an automatic resend.
Pause cannot revoke a transport that already acquired and committed its fence.
Resume increments the generation but never releases uncertain dispatches.
SQL targets PostgreSQL and SQLite; local tests validate SQLite only.
"""
from uuid import uuid4
from sqlalchemy import text


class ControlConflict(Exception):
    """The caller's revision no longer matches current control state."""


def _scope(contact_id, instance):
    if not isinstance(contact_id, int) or contact_id <= 0 or not isinstance(instance, str) or not instance:
        raise ValueError('A contact and nonempty instance are required')
    return {'contact_id': contact_id, 'instance': instance}


def _revision(value):
    return type(value) is int and value >= 0


async def _one(db, sql, params):
    return (await db.execute(text(sql), params)).mappings().first()


async def _lock(db, params):
    # INSERT handles the absent-row race; the no-op UPDATE locks the scope until
    # caller commit/rollback, including at PostgreSQL READ COMMITTED isolation.
    await db.execute(text('''INSERT INTO conversation_controls (contact_id, instance)
        VALUES (:contact_id, :instance) ON CONFLICT (contact_id, instance) DO NOTHING'''), params)
    await db.execute(text('''UPDATE conversation_controls SET revision=revision
        WHERE contact_id=:contact_id AND instance=:instance'''), params)


async def snapshot(db, contact_id, instance):
    row = await _one(db, '''SELECT revision, paused, inflight FROM conversation_controls
        WHERE contact_id=:contact_id AND instance=:instance''', _scope(contact_id, instance))
    if row is None:
        return {'revision': 0, 'paused': False, 'inflight': None}
    return {'revision': int(row['revision']), 'paused': bool(row['paused']), 'inflight': row['inflight']}


async def pause(db, contact_id, instance, event_id, reason, actor_id=None):
    if not event_id:
        raise ValueError('A stable event id is required')
    params = _scope(contact_id, instance)
    params.update(event_id=event_id, reason=reason, actor_id=actor_id, id=str(uuid4()))
    await _lock(db, params)
    duplicate = await _one(db, '''SELECT id FROM conversation_control_audit
        WHERE contact_id=:contact_id AND instance=:instance AND event_id=:event_id''', params)
    if duplicate is None:
        state = await _one(db, '''UPDATE conversation_controls SET revision=revision+1, paused=true
            WHERE contact_id=:contact_id AND instance=:instance RETURNING revision''', params)
        params['revision'] = state['revision']
        await db.execute(text('''INSERT INTO conversation_control_audit
            (id,contact_id,instance,revision,action,event_id,reason,actor_id)
            VALUES (:id,:contact_id,:instance,:revision,'pause',:event_id,:reason,:actor_id)'''), params)
    return await snapshot(db, contact_id, instance)


async def resume(db, contact_id, instance, expected_revision, actor_id):
    if not _revision(expected_revision) or actor_id is None:
        raise ControlConflict('Explicit revision and authenticated actor required')
    params = _scope(contact_id, instance)
    params.update(expected_revision=expected_revision, actor_id=actor_id, id=str(uuid4()))
    await _lock(db, params)
    state = await _one(db, '''UPDATE conversation_controls SET revision=revision+1, paused=false
        WHERE contact_id=:contact_id AND instance=:instance AND revision=:expected_revision
        RETURNING revision''', params)
    if state is None:
        raise ControlConflict('Conversation control revision changed')
    params['revision'] = state['revision']
    await db.execute(text('''INSERT INTO conversation_control_audit
        (id,contact_id,instance,revision,action,actor_id)
        VALUES (:id,:contact_id,:instance,:revision,'resume',:actor_id)'''), params)
    return await snapshot(db, contact_id, instance)


async def allowed(db, contact_id, instance, expected_revision):
    if not _revision(expected_revision):
        return False
    state = await snapshot(db, contact_id, instance)
    return not state['paused'] and state['inflight'] is None and state['revision'] == expected_revision


async def claim_send(db, contact_id, instance, expected_revision, intent_id):
    if not intent_id:
        raise ValueError('A stable intent id is required')
    params = _scope(contact_id, instance)
    params.update(id=intent_id, revision=expected_revision if _revision(expected_revision) else None)
    await _lock(db, params)
    inserted = await _one(db, '''INSERT INTO conversation_send_intents
        (id,contact_id,instance,revision,status) VALUES (:id,:contact_id,:instance,:revision,'suppressed')
        ON CONFLICT (id) DO NOTHING RETURNING id''', params)
    if inserted is None:
        existing = await _one(db, 'SELECT contact_id,instance,status FROM conversation_send_intents WHERE id=:id', params)
        if existing['contact_id'] != contact_id or existing['instance'] != instance:
            return 'suppressed'
        return existing['status']
    claimed = await _one(db, '''UPDATE conversation_controls SET inflight=:id
        WHERE contact_id=:contact_id AND instance=:instance AND revision=:revision
        AND paused=false AND inflight IS NULL RETURNING revision''', params)
    if claimed is None:
        return 'suppressed'
    await db.execute(text("UPDATE conversation_send_intents SET status='needs_review' WHERE id=:id"), params)
    return 'claimed'


async def record_receipt(db, contact_id, instance, receipt_id):
    if not receipt_id:
        raise ValueError('A nonempty provider receipt is required')
    params = _scope(contact_id, instance)
    params['external_id'] = receipt_id
    await db.execute(text('''INSERT INTO conversation_receipts (contact_id,instance,external_id)
        VALUES (:contact_id,:instance,:external_id)
        ON CONFLICT (contact_id,instance,external_id) DO NOTHING'''), params)


async def finish_send(db, intent_id, receipt_id):
    params = {'id': intent_id}
    existing = await _one(db, 'SELECT contact_id,instance,status FROM conversation_send_intents WHERE id=:id', params)
    if existing is None:
        raise ControlConflict('Unknown send intent')
    params.update(contact_id=existing['contact_id'], instance=existing['instance'])
    await _lock(db, params)
    existing = await _one(db, 'SELECT status FROM conversation_send_intents WHERE id=:id', params)
    if existing['status'] != 'needs_review':
        return existing['status']
    await db.execute(text('UPDATE conversation_send_intents SET transport_finished=true WHERE id=:id'), params)
    if not receipt_id:
        return existing['status']
    await record_receipt(db, params['contact_id'], params['instance'], receipt_id)
    params['receipt_id'] = receipt_id
    await db.execute(text("UPDATE conversation_send_intents SET status='sent', receipt_id=:receipt_id WHERE id=:id"), params)
    await db.execute(text('''UPDATE conversation_controls SET inflight=NULL
        WHERE contact_id=:contact_id AND instance=:instance AND inflight=:id'''), params)
    return 'sent'


async def known_receipt(db, contact_id, instance, external_id):
    params = _scope(contact_id, instance)
    params['external_id'] = external_id
    return await _one(db, '''SELECT external_id FROM conversation_receipts
        WHERE contact_id=:contact_id AND instance=:instance AND external_id=:external_id''', params) is not None


async def alert_claim(db, contact_id, instance, dedup_key):
    """Reserve pending notification; enqueue its job in the SAME transaction."""
    if not dedup_key:
        raise ValueError('A stable alert deduplication key is required')
    params = _scope(contact_id, instance)
    params['dedup_key'] = dedup_key
    return await _one(db, '''INSERT INTO conversation_alert_intents (contact_id,instance,dedup_key,status)
        VALUES (:contact_id,:instance,:dedup_key,'pending')
        ON CONFLICT (contact_id,instance,dedup_key) DO NOTHING RETURNING dedup_key''', params) is not None


async def claim_alert(db, contact_id, instance, dedup_key):
    params = _scope(contact_id, instance)
    params['dedup_key'] = dedup_key
    claimed = await _one(db, '''UPDATE conversation_alert_intents SET status='needs_review'
        WHERE contact_id=:contact_id AND instance=:instance AND dedup_key=:dedup_key
        AND status='pending' RETURNING dedup_key''', params)
    if claimed is not None:
        return 'claimed'
    row = await _one(db, '''SELECT status FROM conversation_alert_intents
        WHERE contact_id=:contact_id AND instance=:instance AND dedup_key=:dedup_key''', params)
    return row['status'] if row else 'missing'


async def finish_alert(db, contact_id, instance, dedup_key, receipt_id):
    params = _scope(contact_id, instance)
    params.update(dedup_key=dedup_key, receipt_id=receipt_id)
    await _lock(db, params)
    row = await _one(db, """SELECT status FROM conversation_alert_intents
        WHERE contact_id=:contact_id AND instance=:instance AND dedup_key=:dedup_key""", params)
    if row is None or row['status'] != 'needs_review':
        return row['status'] if row else 'missing'
    await db.execute(text("""UPDATE conversation_alert_intents SET transport_finished=true
        WHERE contact_id=:contact_id AND instance=:instance AND dedup_key=:dedup_key"""), params)
    if receipt_id:
        # Alert scope is its source conversation, not its delivery recipient.
        # The sender records the verified recipient echo ID in this transaction.
        await db.execute(text("""UPDATE conversation_alert_intents SET status='sent',receipt_id=:receipt_id
            WHERE contact_id=:contact_id AND instance=:instance AND dedup_key=:dedup_key"""), params)
        return 'sent'
    return 'needs_review'


def _delivery_scope(contact_id, instance, kind, key):
    params = _scope(contact_id, instance)
    if type(contact_id) is not int or not instance.strip() or len(instance) > 255:
        raise ValueError('A stable conversation scope is required')
    if kind not in ('send', 'alert'):
        raise ValueError('Intent kind must be send or alert')
    if not isinstance(key, str) or not key.strip() or len(key) > 255:
        raise ValueError('A stable intent key is required')
    params['key'] = key
    return params


async def _delivery_intent(db, params, kind):
    # Identifiers come only from the validated kind, never caller SQL.
    table, key_column = ('conversation_send_intents', 'id') if kind == 'send' else ('conversation_alert_intents', 'dedup_key')
    row = await _one(db, f"""SELECT status, receipt_id, transport_finished FROM {table}
        WHERE contact_id=:contact_id AND instance=:instance AND {key_column}=:key""", params)
    if row is None:
        return None
    return {'kind': kind, 'key': params['key'], 'status': row['status'],
            'receipt_id': row['receipt_id'], 'transport_finished': bool(row['transport_finished'])}


async def inspect_delivery(db, contact_id, instance, kind, key):
    """Read scoped metadata only. A snapshot is advisory; close rechecks under lock."""
    params = _delivery_scope(contact_id, instance, kind, key)
    intent = await _delivery_intent(db, params, kind)
    if intent is None:
        return None
    return {'contact_id': contact_id, 'instance': instance, 'intent': intent,
            'control': await snapshot(db, contact_id, instance)}


async def close_unknown(db, contact_id, instance, kind, key, expected_revision, actor_id, reason):
    """Accept uncertainty after a finished local call; never infer non-delivery.

    No transport or receipt assignment occurs. The caller must commit the intent,
    paused control, and audit together. Resume is a separate explicit action.
    Unfinished/crashed calls cannot be released through this operation.
    """
    params = _delivery_scope(contact_id, instance, kind, key)
    if not _revision(expected_revision) or type(actor_id) is not int or actor_id <= 0:
        raise ControlConflict('Explicit revision and authenticated actor required')
    if not isinstance(reason, str) or len(reason) > 500 or len(''.join(reason.split())) < 8:
        raise ValueError('A reason with 8 nonwhitespace characters and at most 500 characters is required')
    await _lock(db, params)
    intent = await _delivery_intent(db, params, kind)
    control = await snapshot(db, contact_id, instance)
    if (intent is None or intent['status'] != 'needs_review' or not intent['transport_finished']
            or control['revision'] != expected_revision
            or (kind == 'send' and control['inflight'] != key)):
        raise ControlConflict('Intent is unfinished, already resolved, or control revision/fence changed')
    table, key_column = ('conversation_send_intents', 'id') if kind == 'send' else ('conversation_alert_intents', 'dedup_key')
    await db.execute(text(f"""UPDATE {table} SET status='closed_unknown'
        WHERE contact_id=:contact_id AND instance=:instance AND {key_column}=:key"""), params)
    clear = ', inflight=NULL' if kind == 'send' else ''
    await db.execute(text(f"""UPDATE conversation_controls SET revision=revision+1, paused=true{clear}
        WHERE contact_id=:contact_id AND instance=:instance"""), params)
    params.update(id=str(uuid4()), prior_revision=expected_revision, revision=expected_revision + 1,
                  actor_id=actor_id, reason=reason, kind=kind)
    await db.execute(text("""INSERT INTO conversation_control_audit
        (id,contact_id,instance,revision,prior_revision,action,actor_id,reason,intent_kind,intent_key)
        VALUES (:id,:contact_id,:instance,:revision,:prior_revision,'close_unknown',:actor_id,:reason,:kind,:key)"""), params)
    return await inspect_delivery(db, contact_id, instance, kind, key)


async def reserve_plain_send(db, contact_id, instance, intent_id):
    """Idempotency and pause fence for a send that holds no conversation fence.

    The pause is checked under the scope lock, and the reservation row is
    inserted in the caller's transaction, which the caller commits before
    transport. Unlike claim_send it never sets `inflight`, so an unresolved
    send cannot freeze the other messages of the same conversation. A retry
    of the same intent finds the row and must not transmit again.
    """
    if not intent_id:
        raise ValueError('A stable intent id is required')
    params = _scope(contact_id, instance)
    params['id'] = intent_id
    await _lock(db, params)
    control = await _one(db, '''SELECT paused FROM conversation_controls
        WHERE contact_id=:contact_id AND instance=:instance''', params)
    if control is not None and bool(control['paused']):
        return 'paused'
    inserted = await _one(db, '''INSERT INTO conversation_send_intents
        (id,contact_id,instance,revision,status) VALUES (:id,:contact_id,:instance,NULL,'needs_review')
        ON CONFLICT (id) DO NOTHING RETURNING id''', params)
    if inserted is None:
        existing = await _one(db, 'SELECT status FROM conversation_send_intents WHERE id=:id', params)
        return 'duplicate:' + existing['status']
    return 'reserved'


async def release_unsent_plain_send(db, intent_id):
    """Drop a plain-send reservation whose transport provably never left this
    process. Only an unfinished needs_review row can be released."""
    await db.execute(text("""DELETE FROM conversation_send_intents
        WHERE id=:id AND status='needs_review' AND transport_finished=false"""), {'id': intent_id})
