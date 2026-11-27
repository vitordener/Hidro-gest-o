# Sistema de Gestão para Loja de Piscinas

Site responsivo (computador, tablet e celular) com banco de dados real (SQLite), login seguro e permissões aplicadas no servidor e no banco.

## Como rodar
```bash
pip install -r requirements.txt
python seed_demo.py        # OPCIONAL: dados fictícios para demonstração (não use em produção)
python app.py              # abre em http://localhost:5000
```
Variáveis de ambiente úteis: `PORT`, `PISCINAS_DB` (caminho do banco), `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` (admin criado na primeira execução), `STORE_TZ`, `AUTO_BACKUP=0`.

**Acessos da demonstração** (só após `seed_demo.py`): admin@loja.com / admin12345 · carlos@, mariana@, rafael@loja.com / vendedor123.
Em produção: NÃO rode o seed, defina `ADMIN_EMAIL`/`ADMIN_PASSWORD` fortes e uma `SECRET_KEY` própria.

## O que já funciona
- Login com senha em hash (scrypt), bloqueio após 5 tentativas, proteção CSRF, cabeçalhos de segurança, troca de senha obrigatória no 1º acesso.
- **Vendedor:** tela inicial com meta, barra de progresso, mensagens em 50/75/90/100% (confete ao bater a meta), comissão prevista/aprovada/paga, NOVA VENDA, minhas vendas, consulta de estoque (sem custos), clientes, comissões e histórico de metas.
- **Administrador:** painel (faturamento × lucro bruto × caixa, filtros por período/vendedor/categoria/produto), vendas (cancelar/estornar, custos reais de frete e instalação), produtos e estoque (entrada/saída/ajuste/histórico), fornecedores, pacotes com componentes, comissões (regras por padrão/categoria/produto/pacote, aprovar/pagar/cancelar), metas, financeiro (fluxo de caixa, contas a receber com parcelas, contas a pagar), relatórios em tela + Excel + PDF, usuários, identidade da loja (nome/logo), backup e registro de auditoria.
- Venda em transação única (estoque, meta, comissão, parcelas), chave de idempotência contra clique duplo, histórico imutável por gatilhos no banco.

## Testes
`python test_api.py` (36 testes: permissões, vendas, estoque, comissões, estornos, financeiro, relatórios, segurança).

## Configuração externa necessária
- **Publicar na internet:** rodar atrás de HTTPS (ex.: `gunicorn -w 2 app:app` + Nginx/Caddy com certificado). Com HTTPS ativo, defina `COOKIE_SECURE=1`.
- **Backups:** o sistema gera 1 backup/dia (14 mantidos) em `data/backups`; copie-os periodicamente para fora do servidor (aba Configurações → Backup).
- **SQLite** atende bem uma loja; para muitos usuários simultâneos, migrar para PostgreSQL exige adaptar `db.py`.
