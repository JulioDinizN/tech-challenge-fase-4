# Self-Healing

Automação que reage ao alerta da Fase 4 e executa a ação corretiva sem intervenção humana, por exemplo `kubectl rollout restart deployment/<serviço>` no namespace `togglemaster`.

Mecanismo pendente de decisão. Requisitos:

- Disparo automático a partir do alerta.
- Permissão mínima: reiniciar Deployments somente no namespace `togglemaster`.
- Nenhuma credencial versionada.
- Registro da execução para evidência no relatório e no vídeo.
