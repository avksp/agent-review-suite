# Безопасность

Bootstrap даёт guidance, а не гарантию безопасности. Модель угроз —
docs/ru/architecture/threat-model.md. Активные проверки живых целей требуют явного
scope и полномочий. Не прикладывайте ключи, личные сессии и secret-bearing raw output
к публичным issues. До настройки hosting сообщайте владельцу приватно; после —
через GitHub private vulnerability reporting, если включён. SLA и detection guarantee
не заявлены. Trust boundaries, лимиты и fail-closed — требования релизов.
0.0.0 не production-ready; поддержка потребует фактической квалификации.
