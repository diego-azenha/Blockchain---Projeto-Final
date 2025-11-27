# deploy_oracle.py (robusto contra BOM/encodings estranhos)
from web3 import Web3
import json, os, sys, traceback

RPC = 'http://127.0.0.1:8545'
ABI_FILE = '_oracle.json'
BYTECODE_FILE = '_oracle.bc'
DEPLOYED_FILE = 'deployed_info.json'

def read_text_file_tolerant(path):
    # tenta várias decodificações e retorna string (ou levanta erro com diagnóstico)
    with open(path, 'rb') as f:
        raw = f.read()
    # quick diagnostic: show first few bytes (hex)
    start_bytes = raw[:8]
    hex_preview = start_bytes.hex()
    # try utf-8-sig first (handles BOM)
    decoders = ['utf-8-sig', 'utf-8', 'latin-1']
    last_exc = None
    for enc in decoders:
        try:
            s = raw.decode(enc)
            # sanity check: JSON must start with [ or { (allow whitespace before)
            if s.lstrip().startswith(('[','{')):
                return s
            # if decode ok but not JSON-like, still return but warn
            return s
        except Exception as e:
            last_exc = e
    # if we get here, none worked
    msg = (
        f"Failed to decode file {path} with tried encodings {decoders}.\n"
        f"First bytes (hex): {hex_preview}\n"
        f"Last exception: {last_exc}\n"
    )
    raise ValueError(msg)

def load_json_tolerant(path):
    txt = read_text_file_tolerant(path)
    try:
        return json.loads(txt)
    except Exception as e:
        # show start of content for debugging
        snippet = txt[:400].replace('\n','\\n')
        raise ValueError(f"Arquivo {path} decodificado mas JSON inválido. snippet: {snippet}\nError: {e}")

# start
if not os.path.exists(ABI_FILE) or not os.path.exists(BYTECODE_FILE):
    print(f"[ERROR] Arquivos {ABI_FILE} e {BYTECODE_FILE} devem existir na pasta atual: {os.getcwd()}")
    sys.exit(1)

# try to load ABI robustly
try:
    abi = load_json_tolerant(ABI_FILE)
except Exception as e:
    print("[ERROR] Falha ao ler ABI:", e)
    traceback.print_exc()
    sys.exit(1)

# read bytecode tolerant (it's typically hex text, possibly with BOM)
try:
    bc_txt = read_text_file_tolerant(BYTECODE_FILE).strip()
    # remove common garbage and quotes
    if bc_txt.startswith('"') and bc_txt.endswith('"'):
        bc_txt = bc_txt[1:-1]
except Exception as e:
    print("[ERROR] Falha ao ler bytecode:", e)
    traceback.print_exc()
    sys.exit(1)

if not bc_txt.startswith('0x'):
    bc_txt = '0x' + bc_txt

# connect to RPC
w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    print(f"[ERROR] Não conectou em {RPC}. Rode `npx hardhat node` em outra janela.")
    sys.exit(1)

acct = None
try:
    acct = w3.eth.accounts[0]
    w3.eth.default_account = acct
except Exception:
    pass

print("Usando RPC:", RPC)
print("Conta default (usada para deploy):", acct)

Contract = w3.eth.contract(abi=abi, bytecode=bc_txt)

# find constructor inputs
constructor_inputs = []
for item in abi:
    if item.get('type') == 'constructor':
        constructor_inputs = item.get('inputs', [])
        break

# helper default values (simple)
def default_for_type(typ):
    if typ.startswith('uint') or typ.startswith('int') or typ in ('uint','int'):
        return 0
    if typ == 'address':
        return acct or ('0x' + '0'*40)
    if typ == 'bool':
        return False
    if typ == 'string':
        return ""
    if typ.startswith('bytes'):
        return b''
    if typ.endswith(']'):
        return []
    return 0

try:
    if not constructor_inputs:
        print("Deploying contract (no constructor args)...")
        tx_hash = Contract.constructor().transact({'from': acct})
    else:
        print("Constructor requires inputs:", [(i['name'], i['type']) for i in constructor_inputs])
        defaults = [default_for_type(inp['type']) for inp in constructor_inputs]
        print("Tentando deploy com valores default:", defaults)
        tx_hash = Contract.constructor(*defaults).transact({'from': acct})
    print("tx_hash:", tx_hash.hex())
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    addr = tx_receipt.contractAddress
    print("Contrato deployado em:", addr)
    with open(DEPLOYED_FILE, 'w', encoding='utf-8') as f:
        json.dump({'address': addr, 'abi': abi}, f)
    print(f"Arquivo salvo: {DEPLOYED_FILE}")
except Exception as e:
    print("[ERROR] Erro durante deploy:", e)
    traceback.print_exc()
    if constructor_inputs:
        print("Constructor signature (inputs):", [(i['name'], i['type']) for i in constructor_inputs])
    sys.exit(1)
