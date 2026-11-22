<html><body>
<h1>Referencia: firmas de webhooks</h1>
<p>Cada entrega trae la cabecera <code>X-Signature: sha256=&lt;hex&gt;</code>, donde el hex es el HMAC-SHA256 del cuerpo crudo con <code>WEBHOOK_SECRET</code> como llave.</p>
<p>Compara en tiempo constante (<code>hmac.compare_digest</code>). Una cabecera sin el prefijo <code>sha256=</code> o vacía es inválida.</p>
{payload}
</body></html>
