<%@ Language="VBScript" %>
<%
' KBO Dashboard: 피드백 수신 엔드포인트
' POST /tools/kbo/feedback.asp
'
' 보안: 파라미터화 쿼리 (SQL 인젝션 방지) + IP 기반 1분 쿨다운 (스팸 방지)

Option Explicit
Response.ContentType = "application/json"
Response.Charset = "UTF-8"

' POST만 허용
If Request.ServerVariables("REQUEST_METHOD") <> "POST" Then
    Response.Status = "405 Method Not Allowed"
    Response.Write "{""error"":""POST only""}"
    Response.End
End If

Dim feedbackText
feedbackText = Trim(Request.Form("feedback"))

' 빈 피드백 거부
If Len(feedbackText) = 0 Then
    Response.Status = "400 Bad Request"
    Response.Write "{""error"":""empty""}"
    Response.End
End If

' 1000자 제한
If Len(feedbackText) > 1000 Then
    feedbackText = Left(feedbackText, 1000)
End If

Dim clientIP
clientIP = Request.ServerVariables("REMOTE_ADDR")

Dim conn
Set conn = Server.CreateObject("ADODB.Connection")
conn.Open Application("DB_CONN_STR")

' --- 스팸 방지: 같은 IP에서 1분 내 재전송 차단 ---
Dim spamCheck, recentCount
Set spamCheck = Server.CreateObject("ADODB.Command")
spamCheck.ActiveConnection = conn
spamCheck.CommandText = "SELECT COUNT(*) FROM KBO_FEEDBACK WHERE ip_address = ? AND created_at > DATEADD(minute, -1, GETDATE())"
spamCheck.Parameters.Append spamCheck.CreateParameter("ip", 200, 1, 45, clientIP)
Set recentCount = spamCheck.Execute

If recentCount(0) > 0 Then
    recentCount.Close
    conn.Close
    Set conn = Nothing
    Response.Status = "429 Too Many Requests"
    Response.Write "{""error"":""too_many_requests""}"
    Response.End
End If
recentCount.Close

' --- 파라미터화 쿼리로 INSERT (SQL 인젝션 완전 차단) ---
Dim cmd
Set cmd = Server.CreateObject("ADODB.Command")
cmd.ActiveConnection = conn
cmd.CommandText = "INSERT INTO KBO_FEEDBACK (feedback_text, created_at, ip_address) VALUES (?, GETDATE(), ?)"
cmd.Parameters.Append cmd.CreateParameter("fb", 203, 1, 1000, feedbackText)
cmd.Parameters.Append cmd.CreateParameter("ip", 200, 1, 45, clientIP)
cmd.Execute

conn.Close
Set conn = Nothing

Response.Write "{""ok"":true}"
%>
