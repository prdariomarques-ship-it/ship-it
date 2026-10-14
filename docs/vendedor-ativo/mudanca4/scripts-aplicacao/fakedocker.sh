#!/bin/bash
# docker de mentira: o "container" e a pasta $FAKE/root; caminhos /app/... sao reescritos para ela.
F="$FAKE"; BK=darioos-evolution-backend-1
map() { echo "${1//\/app\//$F/root/app/}"; }
case "$1" in
  inspect) [ -f "$F/unhealthy" ] && echo unhealthy || echo healthy ;;
  restart) echo restarted >> "$F/events"; [ -f "$F/unhealthy_after_restart" ] && touch "$F/unhealthy"; echo "$BK" ;;
  logs) cat "$F/logs" 2>/dev/null || true ;;
  cp)
    if [[ "$2" == $BK:* ]]; then cp "$(map "${2#$BK:}")" "$3"
    else
      dst="$(map "${3#$BK:}")"
      [ -n "${FAIL_CP_N:-}" ] && { n=$(( $(cat "$F/cpn" 2>/dev/null || echo 0) + 1 )); echo $n > "$F/cpn"; [ "$n" = "$FAIL_CP_N" ] && exit 1; }
      cp "$2" "$dst"
      if [ -n "${CORRUPT_CP:-}" ] && [[ "$dst" == *m4_new ]]; then echo x >> "$dst"; fi
      exit 0
    fi ;;
  exec)
    shift; [ "$1" = "-i" ] && { shift; interactive=1; }; shift   # remove -i e o nome do container
    case "$1" in
      sha256sum) shift; for p in "$@"; do sha256sum "$(map "$p")" | sed "s#$F/root##"; done ;;
      test) shift; [ -e "$(map "$2")" ] ;;
      rm) shift; shift; for p in "$@"; do rm -f "$(map "$p")"; done ;;
      sh) cmd="$(map "$3")"; [ -n "${FAIL_SECOND_MV:-}" ] && cmd="${cmd//mv *messaging.py.m2a_new*/false}"; bash -c "$cmd" ;;
      python) if [ -n "${interactive:-}" ]; then cat > /dev/null; fi; [ -f "$F/smoke_fail" ] && { echo "AssertionError simulado"; exit 1; }; echo "verificação funcional OK" ;;
    esac ;;
esac
