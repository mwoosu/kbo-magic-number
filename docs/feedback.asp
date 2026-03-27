<%@ Language="VBScript" %>
<%
' KBO Dashboard: 피드백 수신 엔드포인트
' POST /kbo/feedback.asp
' Body: feedback=<text>
'
' MSSQL KBO_FEEDBACK 테이블에 INSERT

Option Explicit
Response.ContentType = "application/json"
Response.Charset = "UTF-8"

If Request.ServerVariables("REQUEST_METHOD") <> "POST" Then
    Response.Status = "405 Method Not Allowed"
    Response.Write "{""error"":""POST only""}"
    Response.End
End If

Dim feedbackText
feedbackText = Request.Form("feedback")

If Len(Trim(feedbackText)) = 0 Then
    Response.Status = "400 Bad Request"
    Response.Write "{""error"":""empty feedback""}"
    Response.End
End If

' XSS 방지
feedbackText = Replace(feedbackText, "'", "''")
If Len(feedbackText) > 1000 Then
    feedbackText = Left(feedbackText, 1000)
End If

Dim conn, sql
Set conn = Server.CreateObject("ADODB.Connection")

' 기존 가비아 DB 연결 문자열 사용
' conf/site_config.inc 와 동일하게 설정
conn.Open Application("DB_CONN_STR")

sql = "INSERT INTO KBO_FEEDBACK (feedback_text, created_at, ip_address) " & _
      "VALUES (N'" & feedbackText & "', GETDATE(), '" & Request.ServerVariables("REMOTE_ADDR") & "')"
conn.Execute sql

conn.Close
Set conn = Nothing

Response.Write "{""ok"":true}"
%>
