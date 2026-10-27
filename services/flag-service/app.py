import logging
import os
import sys
from functools import wraps

import psycopg2
import requests
from database_config import build_database_config
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

# Logs no stdout. Com OpenTelemetry ativo, o handler OTLP já está na raiz e
# basicConfig seria ignorado, por isso o handler de console é adicionado explicitamente.
_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
logging.getLogger().addHandler(_console)
logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)

# Carrega .env para desenvolvimento local
load_dotenv() 

app = Flask(__name__)

# --- Configuração ---
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")

if not AUTH_SERVICE_URL:
    log.critical("Erro: AUTH_SERVICE_URL deve ser definida.")
    sys.exit(1)

try:
    DATABASE_CONFIG = build_database_config()
except ValueError as error:
    log.critical(f"Erro: configuração do PostgreSQL inválida: {error}")
    sys.exit(1)

# --- Pool de Conexão com o Banco ---
# Inicializa o pool de conexões (Mín: 1, Máx: 5 conexões)
try:
    # RealDictCursor definido na conexão (e não em cada cursor) para que a
    # instrumentação OpenTelemetry do psycopg2 também rastreie as consultas.
    pool = SimpleConnectionPool(1, 5, cursor_factory=RealDictCursor, **DATABASE_CONFIG)
    log.info("Pool de conexões com o PostgreSQL inicializado.")
except psycopg2.OperationalError as e:
    log.critical(f"Erro fatal ao conectar ao PostgreSQL: {e}")
    sys.exit(1)

# --- Middleware de Autenticação ---
def require_auth(f):
    """ Middleware para validar a chave de API contra o auth-service """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"error": "Authorization header obrigatório"}), 401
        
        try:
            # Chama o /validate do auth-service
            validate_url = f"{AUTH_SERVICE_URL}/validate"
            response = requests.get(validate_url, headers={"Authorization": auth_header}, timeout=3)
            
            if response.status_code != 200:
                log.warning(f"Falha na validação da chave (status: {response.status_code})")
                return jsonify({"error": "Chave de API inválida"}), 401
        
        except requests.exceptions.Timeout:
            log.error("Timeout ao conectar com o auth-service")
            return jsonify({"error": "Serviço de autenticação indisponível (timeout)"}), 504 # Gateway Timeout
        except requests.exceptions.RequestException as e:
            log.error(f"Erro ao conectar com o auth-service: {e}")
            return jsonify({"error": "Serviço de autenticação indisponível"}), 503 # Service Unavailable

        # Se a chave for válida, continua para a rota
        return f(*args, **kwargs)
    return decorated

# --- Endpoints da API ---

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/flags', methods=['POST'])
@require_auth
def create_flag():
    """ Cria uma nova definição de feature flag """
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "'name' é obrigatório"}), 400
    
    name = data['name']
    description = data.get('description', '')
    is_enabled = data.get('is_enabled', False)
    
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO flags (name, description, is_enabled, created_at, updated_at) "
            "VALUES (%s, %s, %s, NOW(), NOW()) RETURNING *",
            (name, description, is_enabled)
        )
        new_flag = cur.fetchone()
        conn.commit()
        log.info(f"Flag '{name}' criada com sucesso.")
        return jsonify(new_flag), 201
    except psycopg2.IntegrityError:
        if conn: conn.rollback()
        log.warning(f"Tentativa de criar flag duplicada: '{name}'")
        return jsonify({"error": f"Flag '{name}' já existe"}), 409
    except Exception as e:
        if conn: conn.rollback()
        log.exception("Erro ao criar flag")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags', methods=['GET'])
@require_auth
def get_flags():
    """ Lista todas as feature flags """
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM flags ORDER BY name")
        flags = cur.fetchall()
        return jsonify(flags)
    except Exception as e:
        log.exception("Erro ao buscar flags")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags/<string:name>', methods=['GET'])
@require_auth
def get_flag(name):
    """ Busca uma feature flag específica pelo nome """
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM flags WHERE name = %s", (name,))
        flag = cur.fetchone()
        if not flag:
            return jsonify({"error": "Flag não encontrada"}), 404
        return jsonify(flag)
    except Exception as e:
        log.exception("Erro ao buscar flag '{name}'")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags/<string:name>', methods=['PUT'])
@require_auth
def update_flag(name):
    """ Atualiza uma feature flag (descrição ou status 'is_enabled') """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Corpo da requisição obrigatório"}), 400

    fields = []
    values = []
    
    # Constrói a query dinamicamente
    if 'description' in data:
        fields.append("description = %s")
        values.append(data['description'])
    if 'is_enabled' in data:
        fields.append("is_enabled = %s")
        values.append(data['is_enabled'])
    
    if not fields:
        return jsonify({"error": "Pelo menos um campo ('description', 'is_enabled') é obrigatório"}), 400
    
    values.append(name) # Adiciona o 'name' para a cláusula WHERE
    
    query = sql.SQL("UPDATE flags SET {} WHERE name = %s RETURNING *").format(sql.SQL(", ").join(sql.SQL(field) for field in fields))
    
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(query, tuple(values))
        
        if cur.rowcount == 0:
            return jsonify({"error": "Flag não encontrada"}), 404
            
        updated_flag = cur.fetchone()
        conn.commit()
        log.info(f"Flag '{name}' atualizada com sucesso.")
        return jsonify(updated_flag), 200
    except Exception as e:
        if conn: conn.rollback()
        log.exception("Erro ao atualizar flag '{name}'")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

@app.route('/flags/<string:name>', methods=['DELETE'])
@require_auth
def delete_flag(name):
    """ Deleta uma feature flag """
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute("DELETE FROM flags WHERE name = %s", (name,))
        
        if cur.rowcount == 0:
            return jsonify({"error": "Flag não encontrada"}), 404
            
        conn.commit()
        log.info(f"Flag '{name}' deletada com sucesso.")
        return "", 204 # 204 No Content
    except Exception as e:
        if conn: conn.rollback()
        log.exception("Erro ao deletar flag '{name}'")
        return jsonify({"error": "Erro interno do servidor", "details": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: pool.putconn(conn)

if __name__ == '__main__':
    port = int(os.getenv("PORT", "8002"))
    app.run(host='0.0.0.0', port=port, debug=False)  # nosec B104
