"""
Parser per i file XML/AML esportati da ARIS.
Estrae oggetti (con GUID, nome, tipo) e connessioni dal formato AML nativo.

L'XML è l'as-is: il modello come esiste nel database ARIS.
Il pipeline confronta il Word to-be (modificato dal PO) con l'XML as-is
per determinare le operazioni di aggiornamento.

Struttura AML:
- <ObjDef> contiene oggetti con GUID, tipo, nome, e connessioni figlie
- <CxnDef> dentro ObjDef: connessione da source (parent) a target (ToObjDef.IdRef)
- <Model> contiene <ObjOcc> (occorrenze nel diagramma) con link a ObjDef
"""

import xml.etree.ElementTree as ET


def parse_xml(filepath: str) -> dict:
    """
    Parsa un file XML/AML di ARIS e restituisce un dizionario
    compatibile con il formato JSON del Resolver.

    Returns:
        dict con chiavi:
        - 'modelobjects': lista di oggetti (come nel JSON API)
        - 'modelconnections': lista di connessioni (come nel JSON API)
        - 'metadata': info sul modello (nome, database, data export)
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    # --- Metadata ---
    header = root.find('Header-Info')
    metadata = {}
    if header is not None:
        metadata = {
            'database': header.get('DatabaseName', ''),
            'export_date': header.get('CreateDate', ''),
            'export_time': header.get('CreateTime', ''),
        }

    # --- Mappa ID interno -> GUID e nome ---
    id_to_guid = {}
    id_to_name = {}
    id_to_type = {}
    id_to_symbol = {}

    for obj in root.iter('ObjDef'):
        obj_id = obj.get('ObjDef.ID')
        guid_el = obj.find('GUID')
        if guid_el is not None:
            id_to_guid[obj_id] = guid_el.text
        id_to_type[obj_id] = obj.get('TypeNum', '')
        id_to_symbol[obj_id] = obj.get('SymbolNum', '')

        # Estrai nome
        for attr in obj.iter('AttrDef'):
            if attr.get('AttrDef.Type') == 'AT_NAME':
                plain = attr.find('.//PlainText')
                if plain is not None:
                    id_to_name[obj_id] = plain.get('TextValue', '')
                    break

    # --- Oggetti (formato compatibile JSON API) ---
    modelobjects = []
    seen_guids = set()

    for obj in root.iter('ObjDef'):
        obj_id = obj.get('ObjDef.ID')
        guid = id_to_guid.get(obj_id, '')
        name = id_to_name.get(obj_id, '')
        type_num = id_to_type.get(obj_id, '')
        symbol = id_to_symbol.get(obj_id, '')

        if not guid or guid in seen_guids:
            continue
        seen_guids.add(guid)

        # Mappa tipo XML -> tipo JSON
        type_map = {
            'OT_FUNC': 'Function',
            'OT_EVT': 'Event',
            'OT_ORG_UNIT': 'Organizational unit',
            'OT_APPL_SYS_TYPE': 'Application system type',
            'OT_RULE': 'Rule',
            'OT_PERS_TYPE': 'Person type',
            'OT_APPL_SYS_CLS': 'Application system class',
        }

        modelobjects.append({
            'kind': 'MODELOBJECT',
            'guid': guid,
            'type': type_num,
            'typename': type_map.get(type_num, type_num),
            'apiname': type_num,
            'symbolname': symbol,
            'attributes': [{
                'kind': 'ATTRIBUTE',
                'typename': 'Name',
                'apiname': 'AT_NAME',
                'value': name,
            }],
        })

    # --- Connessioni ---
    modelconnections = []

    # Le connessioni in AML sono figlie dell'ObjDef source
    for obj in root.iter('ObjDef'):
        source_id = obj.get('ObjDef.ID')
        source_guid = id_to_guid.get(source_id, '')

        for cxn in obj.findall('CxnDef'):
            target_id = cxn.get('ToObjDef.IdRef', '')
            target_guid = id_to_guid.get(target_id, '')
            cxn_type = cxn.get('CxnDef.Type', '')

            # Mappa tipo connessione
            cxn_type_map = {
                'CT_EXEC_1': 'carries out',
                'CT_CAN_SUPP_1': 'supports',
                'CT_ACTIV_1': 'activates',
                'CT_CRT_1': 'creates',
                'CT_LEADS_TO_1': 'leads to',
                'CT_LEADS_TO_2': 'leads to',
                'CT_IS_PREDEC_OF_1': 'is predecessor of',
                'CT_IS_EVAL_BY_1': 'is evaluated by',
                'CT_LNK_2': 'contributes to',
                'CT_BELONGS_TO_CLS': 'belongs to',
                'CT_WRK_IN': 'works in',
                'CT_IS_TECH_RESP_1': 'is technically responsible for',
                'CT_IS_SUPERIOR_1': 'is superior of',
                'CT_IS_PRCS_ORNT_SUPER': 'is process-oriented superior',
            }

            if source_guid and target_guid:
                modelconnections.append({
                    'kind': 'MODELCONNECTION',
                    'type': cxn_type,
                    'typename': cxn_type_map.get(cxn_type, cxn_type),
                    'apiname': cxn_type,
                    'source_guid': source_guid,
                    'target_guid': target_guid,
                })

    return {
        'metadata': metadata,
        'modelobjects': modelobjects,
        'modelconnections': modelconnections,
    }


def summarize_xml(parsed: dict) -> str:
    """Produce un riepilogo leggibile del contenuto XML."""
    objs = parsed['modelobjects']
    cxns = parsed['modelconnections']
    meta = parsed.get('metadata', {})

    from collections import Counter
    obj_types = Counter(o['typename'] for o in objs)
    cxn_types = Counter(c['typename'] for c in cxns)

    lines = []
    lines.append(f"Database: {meta.get('database', '?')}")
    lines.append(f"Export: {meta.get('export_date', '?')} {meta.get('export_time', '?')}")
    lines.append(f"Oggetti: {len(objs)} ({dict(obj_types)})")
    lines.append(f"Connessioni: {len(cxns)} ({dict(cxn_types)})")
    return "\n".join(lines)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python xml_parser.py <file.xml>")
        sys.exit(1)

    parsed = parse_xml(sys.argv[1])
    print(summarize_xml(parsed))

    print("\n=== ATTIVITÀ ===")
    for obj in parsed['modelobjects']:
        if obj['typename'] == 'Function':
            name = obj['attributes'][0]['value']
            print(f"  {name} ({obj['guid'][:8]}...)")

    print(f"\n=== CONNESSIONI 'carries out' ===")
    guid_to_name = {o['guid']: o['attributes'][0]['value'] for o in parsed['modelobjects']}
    for cxn in parsed['modelconnections']:
        if cxn['typename'] == 'carries out':
            src = guid_to_name.get(cxn['source_guid'], '?')
            tgt = guid_to_name.get(cxn['target_guid'], '?')
            print(f"  {src} → {tgt}")