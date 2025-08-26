import cx_Oracle
from conexao_oracle_teste import conectar_oracle 
import pandas as pd
from fastapi import FastAPI, Form, Request, Depends, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import io
import secrets
import signal
from typing import Optional
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
import re
from fastapi import Query

app = FastAPI()

# Configurar CORS para permitir acesso externo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar templates
templates = Jinja2Templates(directory="templates")

# Variável global para o base URL
BASE_URL = "/consulta-select"

# Configuração de timeout (1200 segundos)
QUERY_TIMEOUT = 1200  # segundos

# Configuração de segurança
SECRET_KEY = "sua_chave_secreta_aqui"
SESSION_COOKIE_NAME = "session_token"

# Dicionário simples para armazenar sessões
sessions = {}

# Função para executar query com timeout
def executar_query_com_timeout(query, params=None):
    """
    Executa uma query Oracle com timeout
    """
    def executar_query():
        try:
            conexao = conectar_oracle()
            cursor = conexao.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            resultados = cursor.fetchall()
            colunas = [desc[0] for desc in cursor.description]
            
            conexao.close()
            return {"success": True, "resultados": resultados, "colunas": colunas}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # Executar a query com timeout
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(executar_query)
        try:
            resultado = future.result(timeout=QUERY_TIMEOUT)
            return resultado
        except FutureTimeoutError:
            return {"success": False, "error": f"Timeout: A query excedeu o tempo limite de {QUERY_TIMEOUT} segundos"}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Função para registrar log da consulta
def registrar_log_consulta(usuario: str, query_sql: str, status: str, 
                          mensagem_erro: str = None, tempo_execucao: float = None,
                          request: Request = None):
    try:
        conexao = conectar_oracle()
        cursor = conexao.cursor()
        
        # Obter informações do cliente
        ip_cliente = None
        user_agent = None
        
        if request:
            try:
                ip_cliente = request.client.host if request.client else "Desconhecido"
                user_agent = request.headers.get("user-agent", "Desconhecido")
            except:
                ip_cliente = "Erro ao obter IP"
                user_agent = "Erro ao obter User-Agent"
        
        insert_query = """
                """
        
        cursor.execute(insert_query, {
            'usuario': usuario,
            'query_sql': query_sql,
            'ip_cliente': ip_cliente,
            'user_agent': user_agent,
            'status': status,
            'mensagem_erro': mensagem_erro,
            'tempo_execucao': tempo_execucao
        })
        
        conexao.commit()
        conexao.close()
        print(f"Log registrado para usuário: {usuario}, Status: {status}")
        
    except Exception as e:
        print(f"Erro ao registrar log: {e}")
        # Não falhar a aplicação se o log der erro

# Função para obter usuário da sessão
def obter_usuario_logado(request: Request):
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token and session_token in sessions:
        return sessions[session_token]["usuario"]
    return "Usuário Desconhecido"

# Função para verificar credenciais com timeout
def verificar_login(usuario: str, senha: str):
    try:
        query = """
               """
        
        resultado = executar_query_com_timeout(query, {"usuario": usuario.upper()})
        
        if not resultado["success"]:
            print(f"Erro na query de login: {resultado['error']}")
            return False
        
        if resultado["resultados"]:
            senha_db, nome_grupo, codusuario = resultado["resultados"][0]
            print(f"DEBUG - Usuário: {usuario}, Senha DB: '{senha_db}', Grupo: '{nome_grupo}'")
            
            # Verificar se a senha corresponde e se está no grupo correto
            if senha_db and senha_db.strip() == senha.strip() and nome_grupo == 'plsql':
                print("DEBUG - Login válido!")
                return True
            else:
                print(f"DEBUG - Senha não corresponde ou grupo inválido. Grupo esperado: 'plsql', Grupo encontrado: '{nome_grupo}'")
        
        return False
        
    except Exception as e:
        print(f"Erro na verificação de login: {e}")
        import traceback
        traceback.print_exc()
        return False


# Dicionário simples para armazenar sessões (em produção use Redis ou database)
sessions = {}

def criar_sessao(usuario: str):
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = {
        "usuario": usuario,
        "timestamp": datetime.now()
    }
    return session_token

def verificar_sessao(session_token: Optional[str] = Cookie(default=None)):
    if session_token and session_token in sessions:
        return True
    return False

# Rota de login
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "base_url": BASE_URL
    })

# Adicionar também logging no login
@app.post("/login")
async def login(request: Request, usuario: str = Form(...), senha: str = Form(...)):
    start_time = time.time()
    
    if verificar_login(usuario, senha):
        # Login bem-sucedido - criar sessão
        session_token = criar_sessao(usuario)
        response = RedirectResponse(url=BASE_URL + "/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key=SESSION_COOKIE_NAME, value=session_token, httponly=True)
        
        registrar_log_consulta(
            usuario=usuario,
            query_sql="LOGIN",
            status="SUCESSO",
            tempo_execucao=time.time() - start_time,
            request=request
        )
        
        return response
    else:
        tempo_execucao = time.time() - start_time
        registrar_log_consulta(
            usuario=usuario,
            query_sql="TENTATIVA_LOGIN",
            status="ERRO",
            mensagem_erro="Credenciais inválidas",
            tempo_execucao=tempo_execucao,
            request=request
        )
        
        return templates.TemplateResponse("login_error.html", {
            "request": request,
            "error": "Usuário ou senha inválidos. Verifique se está no grupo PLSQL.",
            "base_url": BASE_URL
        })

# Rota de logout
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

# Middleware para verificar autenticação
async def verificar_autenticacao(request: Request):
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not verificar_sessao(session_token):
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, detail="Not authenticated", headers={"Location": "/login"})

# Proteger as rotas existentes
@app.get(BASE_URL + "/", response_class=HTMLResponse)
async def home(request: Request):
    await verificar_autenticacao(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "base_url": BASE_URL
    })

# Modificar a função execute_query para incluir logging
@app.post(BASE_URL + "/execute-query", response_class=HTMLResponse)
async def execute_query(request: Request, sql_query: str = Form(...)):
    usuario = obter_usuario_logado(request)
    start_time = time.time()
    tempo_execucao = None
    
    try:
        await verificar_autenticacao(request)
        
        # Validação básica de segurança
        if not sql_query.strip().lower().startswith('select'):
            error_msg = "Apenas queries SELECT são permitidas por questões de segurança."
            registrar_log_consulta(
                usuario=usuario,
                query_sql=sql_query,
                status="ERRO",
                mensagem_erro=error_msg,
                request=request
            )
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": error_msg,
                "query": sql_query,
                "base_url": BASE_URL
            })
        
        # Executar query com timeout
        resultado = executar_query_com_timeout(sql_query)
        tempo_execucao = time.time() - start_time
        
        if not resultado["success"]:
            registrar_log_consulta(
                usuario=usuario,
                query_sql=sql_query,
                status="ERRO",
                mensagem_erro=resultado["error"],
                tempo_execucao=tempo_execucao,
                request=request
            )
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": resultado["error"],
                "query": sql_query,
                "base_url": BASE_URL
            })
        
        resultados = resultado["resultados"]
        colunas = resultado["colunas"]
        
        # Registrar log de sucesso
        registrar_log_consulta(
            usuario=usuario,
            query_sql=sql_query,
            status="SUCESSO",
            tempo_execucao=tempo_execucao,
            request=request
        )
        
        # Converter para DataFrame para exportação
        df = pd.DataFrame(resultados, columns=colunas)
        
        # Gerar HTML para exibição
        resultados_html = ""
        if resultados:
            for resultado in resultados:
                resultados_html += f"""
                <tr class="hover:bg-gray-50 transition-colors">
                    {"".join([f'<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{str(valor) if valor is not None else "NULL"}</td>' for valor in resultado])}
                </tr>
                """
        
        return templates.TemplateResponse("results.html", {
            "request": request,
            "query": sql_query,
            "resultados_html": resultados_html,
            "colunas": colunas,
            "resultados": resultados,
            "total_registros": len(resultados),
            "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            "dataframe": df.to_json(),
            "base_url": BASE_URL
        })
        
    except Exception as e:
        tempo_execucao = time.time() - start_time
        registrar_log_consulta(
            usuario=usuario,
            query_sql=sql_query,
            status="ERRO",
            mensagem_erro=str(e),
            tempo_execucao=tempo_execucao,
            request=request
        )
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e),
            "query": sql_query,
            "base_url": BASE_URL
        })

# Adicionar rota para visualizar os logs (apenas para administradores)
@app.get(BASE_URL + "/logs", response_class=HTMLResponse)
async def visualizar_logs(request: Request, limit: int = 100):
    await verificar_autenticacao(request)
    
    try:
        query = """
                """
        
        resultado = executar_query_com_timeout(query, {"limit": limit})
        
        if not resultado["success"]:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": resultado["error"],
                "base_url": BASE_URL
            })
        
        logs = resultado["resultados"]
        colunas = resultado["colunas"]
        
        # Gerar HTML para exibição
        logs_html = ""
        if logs:
            for log in logs:
                logs_html += f"""
                <tr class="hover:bg-gray-50 transition-colors">
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{log[0]}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{log[1]}</td>
                    <td class="px-6 py-4 text-sm text-gray-900">
                        <div class="max-w-md overflow-x-auto">
                            <code class="text-xs">{log[2][:100]}{'...' if len(str(log[2])) > 100 else ''}</code>
                        </div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{log[3].strftime('%d/%m/%Y %H:%M:%S') if log[3] else 'N/A'}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{log[4] or 'N/A'}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm">
                        <span class="px-2 py-1 rounded-full text-xs font-medium 
                            {'bg-green-100 text-green-800' if log[5] == 'SUCESSO' else 'bg-red-100 text-red-800'}">
                            {log[5]}
                        </span>
                    </td>
                    <td class="px-6 py-4 text-sm text-gray-900">{log[6] or 'N/A'}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{log[7] or 'N/A'}</td>
                </tr>
                """
        
        return templates.TemplateResponse("logs.html", {
            "request": request,
            "logs_html": logs_html,
            "colunas": ["ID", "Usuário", "Query", "Data/Hora", "IP", "Status", "Erro", "Tempo(s)"],
            "total_logs": len(logs),
            "base_url": BASE_URL
        })
        
    except Exception as e:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e),
            "base_url": BASE_URL
        })

@app.post(BASE_URL + "/export-xlsx")
async def export_xlsx(request: Request):
    await verificar_autenticacao(request)
    form_data = await request.form()
    dataframe_json = form_data.get("dataframe")
    
    if not dataframe_json:
        return HTMLResponse(content="<h1>Erro: Nenhum dado para exportar</h1>")
    
    try:
        df = pd.read_json(dataframe_json)
        
        # Criar arquivo Excel em memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Resultados', index=False)
            
            # Formatação
            workbook = writer.book
            worksheet = writer.sheets['Resultados']
            
            # Formatar cabeçalho
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#4F81BD',
                'font_color': 'white',
                'border': 1
            })
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Auto-ajustar largura das colunas
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
        
        output.seek(0)
        
        # Retornar arquivo para download
        filename = f"resultados_consulta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        return HTMLResponse(content=f"<h1>Erro ao exportar: {str(e)}</h1>")
    
@app.get(BASE_URL + "/autocomplete")
async def autocomplete(alias: str = Query(...), sql: str = Query(...)):
    try:
        padrao = re.compile(rf"([\w\.]+)\s+{alias}\b", re.IGNORECASE)
        match = padrao.search(sql)

        if not match:
            return {"success": False, "error": f"Alias '{alias}' não encontrado no SQL."}

        tabela_completa = match.group(1).upper()

        if "." in tabela_completa:
            schema, tabela = tabela_completa.split(".")
        else:
            schema, tabela = "USER", tabela_completa

        # Consulta no DBLINK
        query = """
        SELECT column_name,
               data_type || 
               CASE 
                 WHEN data_type LIKE '%CHAR%' THEN '(' || data_length || ')'
                 WHEN data_type = 'NUMBER' AND data_precision IS NOT NULL 
                      THEN '(' || data_precision || NVL2(data_scale, ',' || data_scale, '') || ')'
                 ELSE ''
               END AS data_type
        FROM all_tab_columns@dblink
        WHERE UPPER(table_name) = UPPER(:tabela)
          AND UPPER(owner) = UPPER(:schema)
        ORDER BY column_id
        """

        resultado = executar_query_com_timeout(query, {"tabela": tabela, "schema": schema})

        if not resultado["success"]:
            return resultado

        colunas = [{"name": r[0], "type": r[1]} for r in resultado["resultados"]]

        return {"success": True, "alias": alias, "table": tabela, "columns": colunas}

    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get(BASE_URL + "/autocomplete-tables")
async def autocomplete_tables(prefix: str = Query(...)):
    """
    Autocompletar nomes de tabelas baseado em um prefixo
    Exemplo: consinco.mfl -> retorna todas as tabelas que começam com 'mfl' no schema 'consinco'
    """
    try:
        # Verificar se o prefixo contém um ponto (schema.tabela)
        if '.' in prefix:
            schema, table_prefix = prefix.split('.')
            schema = schema.upper()
            table_prefix = table_prefix.upper()
        else:
            # Se não tiver ponto, buscar no schema padrão do usuário
            schema = "USER"
            table_prefix = prefix.upper()
        
        # Consultar tabelas que correspondem ao prefixo
        query = """
        SELECT table_name 
        FROM all_tables@dblink
        WHERE UPPER(owner) = UPPER(:schema)
          AND UPPER(table_name) LIKE UPPER(:table_prefix) || '%'
        ORDER BY table_name
        FETCH FIRST 20 ROWS ONLY
        """
        
        resultado = executar_query_com_timeout(query, {
            "schema": schema,
            "table_prefix": table_prefix
        })
        
        if not resultado["success"]:
            return resultado
        
        tabelas = [r[0] for r in resultado["resultados"]]
        
        return {
            "success": True, 
            "tabelas": tabelas,
            "schema": schema,
            "prefix": table_prefix
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# Redirecionar da raiz para login
@app.get("/")
async def redirect_to_login():
    return RedirectResponse(url="/login")

# Rota para verificar saúde da aplicação
@app.get("/health")
async def health_check():
    return {"status": "ok"}
