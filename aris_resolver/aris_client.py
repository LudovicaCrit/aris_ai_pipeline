"""
Client per l'API REST di ARIS Repository.
Puro Python — nessuna dipendenza da LLM.

Responsabilità:
- Autenticazione (token UMC)
- Ricerca oggetti, modelli, gruppi
- Lettura contenuto modelli
- Creazione/aggiornamento oggetti (futuro)
"""

import requests
import urllib3
from config import ARIS_BASE_URL, ARIS_DB_NAME, ARIS_TENANT

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ARISClient:
    """Client per l'API REST di ARIS Repository."""

    def __init__(self, base_url: str = ARIS_BASE_URL,
                 db_name: str = ARIS_DB_NAME,
                 tenant: str = ARIS_TENANT):
        self.base_url = base_url.rstrip("/")
        self.db_name = db_name
        self.tenant = tenant
        self.token = None
        self.session = requests.Session()
        self.session.verify = False

    def login(self, username: str, password: str) -> bool:
        """Ottiene un token UMC per l'autenticazione API."""
        url = f"{self.base_url}/umc/api/v2/tokens"
        params = {"tenant": self.tenant, "name": username, "password": password}
        try:
            resp = self.session.post(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            self.token = data["token"]
            print(f"[ARIS] Login riuscito.")
            return True
        except Exception as e:
            print(f"[ARIS ERRORE] Login fallito: {e}")
            return False

    def logout(self):
        """Rilascia il token UMC."""
        if self.token:
            url = f"{self.base_url}/umc/api/tokens/{self.token}"
            try:
                self.session.delete(url)
                print("[ARIS] Logout completato.")
            except Exception:
                pass
            self.token = None

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Chiamata GET generica."""
        if params is None:
            params = {}
        params["umcsession"] = self.token
        url = f"{self.base_url}/abs/api/{endpoint}"
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, data: dict = None, params: dict = None) -> dict:
        """Chiamata POST generica."""
        if params is None:
            params = {}
        params["umcsession"] = self.token
        url = f"{self.base_url}/abs/api/{endpoint}"
        resp = self.session.post(url, json=data, params=params)
        resp.raise_for_status()
        return resp.json()

    def _db_encoded(self) -> str:
        return self.db_name.replace(" ", "%20")

    # --- LETTURA ---

    def list_databases(self) -> list:
        """Lista dei database disponibili."""
        result = self._get("databases")
        return result.get("items", [])

    def find_objects(self, name: str, object_types: list = None,
                     language: str = "it", pagesize: int = 50) -> list:
        """Cerca oggetti nel database per nome."""
        params = {
            "kind": "OBJECT",
            "language": language,
            "attrfilter": f"AT_NAME={name}",
            "attributes": "all",
            "pagesize": pagesize
        }
        if object_types:
            params["typefilter"] = ",".join(str(t) for t in object_types)
        try:
            result = self._get(f"databases/{self._db_encoded()}/find", params)
            return result.get("items", [])
        except Exception as e:
            print(f"  [ARIS WARN] Ricerca fallita per '{name}': {e}")
            return []

    def find_models(self, name: str = None, language: str = "it",
                    pagesize: int = 20) -> list:
        """Cerca modelli nel database."""
        params = {
            "kind": "MODEL",
            "language": language,
            "pagesize": pagesize
        }
        if name:
            params["attrfilter"] = f"AT_NAME={name}"
        result = self._get(f"databases/{self._db_encoded()}/find", params)
        return result.get("items", [])

    def get_model_content(self, model_guid: str, language: str = "it") -> dict:
        """Recupera il contenuto completo di un modello."""
        params = {
            "withcontent": "true",
            "language": language,
            "attributes": "all"
        }
        result = self._get(f"models/{self._db_encoded()}/{model_guid}", params)
        if result.get("items"):
            return result["items"][0]
        return {}

    def get_group_children(self, group_guid: str, language: str = "it") -> list:
        """Recupera i figli di un gruppo."""
        params = {
            "withmodels": "true",
            "withobjects": "true",
            "language": language
        }
        result = self._get(f"groups/{self._db_encoded()}/{group_guid}/children", params)
        return result.get("items", [])

    # --- SCRITTURA ---

    def create_group(self, parent_guid: str, name: str, language: str = "it") -> dict:
        """Crea un nuovo gruppo (cartella)."""
        params = {
            "language": language,
            "parent": parent_guid
        }
        data = {"attributes": [{"type": "AT_NAME", "value": name}]}
        return self._post(f"groups/{self._db_encoded()}", data=data, params=params)

    def create_object(self, type_num: int, name: str, group_guid: str,
                      language: str = "it", attributes: list = None) -> dict:
        """Crea un nuovo oggetto (definizione)."""
        attrs = [{"type": "AT_NAME", "value": name}]
        if attributes:
            attrs.extend(attributes)
        data = {
            "type": type_num,
            "group": group_guid,
            "attributes": attrs
        }
        return self._post(f"objects/{self._db_encoded()}", data=data, params={"language": language})
