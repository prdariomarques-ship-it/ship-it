param($email,$pw)
$b='http://127.0.0.1:18000/api'
$r=Invoke-RestMethod -Method Post -Uri "$b/auth/login" -ContentType 'application/json' -Body (@{email=$email;password=$pw}|ConvertTo-Json)
$h=@{Authorization="Bearer $($r.access_token)"}
foreach($p in 'status','metrics','paused-conversations','tasks?limit=3','whatsapp-routing'){ try{ "== $p"; (Invoke-RestMethod "$b/admin/darius/$p" -Headers $h | ConvertTo-Json -Depth 6 -Compress) }catch{ "ERR $p -> $($_.Exception.Response.StatusCode.value__)" } }
