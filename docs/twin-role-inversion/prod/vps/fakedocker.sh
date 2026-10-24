#!/bin/bash
# docker de mentira: o "container" é a pasta $FAKE/root; caminhos /app/... são reescritos para ela.
F="$FAKE"; BK=darioos-evolution-backend-1
map() { printf "%s\n" "${1//\/app\//$F/root/app/}"; }
case "$1" in
  inspect) [ -f "$F/unhealthy" ] && echo unhealthy || echo healthy ;;
  restart) echo restarted >> "$F/events"; [ -f "$F/unhealthy_after_restart" ] && touch "$F/unhealthy"; [ -f "$F/healthy_again_after_second_restart" ] && [ "$(grep -c restarted "$F/events")" -ge 2 ] && rm -f "$F/unhealthy"; echo "$BK" ;;
  cp)
    if [[ "$2" == $BK:* ]]; then cp "$(map "${2#$BK:}")" "$3"
    else
      dst="$(map "${3#$BK:}")"; cp "$2" "$dst"
      if [ -n "${CORRUPT_CP:-}" ] && [[ "$dst" == *main.py.lw_new ]]; then echo x >> "$dst"; fi
      exit 0
    fi ;;
  exec)
    shift
    while [[ "$1" == -* ]]; do case "$1" in -i) interactive=1; shift ;; -e) shift 2 ;; *) shift ;; esac; done
    shift   # nome do container
    case "$1" in
      sha256sum) shift; for p in "$@"; do sha256sum "$(map "$p")" | sed "s#$F/root##"; done ;;
      rm) shift; shift; for p in "$@"; do rm -f "$(map "$p")"; done ;;
      test) shift; [ "$1" = "-f" ] && { [ -f "$(map "$2")" ]; exit $?; }; [ "$1" = "!" ] && shift; [ "$1" = "-e" ] && { [ ! -e "$(map "$2")" ]; exit $?; }; exit 1 ;;
      printenv) [ -n "${FAKE_ENV_PHONE:-}" ] && echo "$FAKE_ENV_PHONE" || exit 1 ;;
      sh) cmd="$(map "$3")"; [ -n "${FAIL_SWAP:-}" ] && cmd="${cmd//mv */false}"; bash -c "$cmd" ;;
      python)
        if [ "$2" = "-c" ]; then echo "limpeza de jobs" >> "$F/events"; echo "jobs lines.watch removidos: 1"; exit 0; fi
        [ -n "${interactive:-}" ] && cat > /dev/null
        n=$(( $(cat "$F/pycalls" 2>/dev/null || echo 0) + 1 )); echo $n > "$F/pycalls"
        if [ -f "$F/smoke_fail" ] && [ "$n" = "${FAIL_PY_N:-1}" ]; then echo "AssertionError simulado"; exit 1; fi
        echo "python ok (chamada $n)"; if [ -n "${PY_REMOVES_JOBS:-}" ]; then echo "limpeza de jobs" >> "$F/events"; fi; exit 0 ;;
    esac ;;
esac
