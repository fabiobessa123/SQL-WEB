# 🔎 Consulta SQL Oracle

Este projeto é uma aplicação para execução controlada de queries `SELECT` em um banco **Oracle**, com autenticação de usuários, controle de sessão e logging de consultas.

## 🚀 Funcionalidades

- Login de usuário com verificação no banco de dados
- Sessão segura via cookies
- Execução de queries `SELECT` com **timeout configurável**
- Exportação de resultados para **Excel (.xlsx)**
- Registro de logs de consultas no banco
- Autocomplete de tabelas e colunas
- Rotas protegidas por autenticação
- Health check da aplicação
- 
- 🔍 Rotas Principais

/login → Tela de login

/consulta-select/ → Página inicial da aplicação (após login)

/consulta-select/execute-query → Executa queries SELECT

/consulta-select/export-xlsx → Exporta resultados para Excel
