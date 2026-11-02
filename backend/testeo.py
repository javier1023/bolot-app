"""Isolated training log: no service key or private data reaches the browser."""
import json
import os
import urllib.request
import urllib.parse
from models.game import cartas_jugables, Fase

HUMANS = (0, 2)


def observation(estado, actor):
    view = estado.to_dict_para(actor)
    # to_dict_para emits public declarations and exactly one private hand.
    return {k: view[k] for k in (
        'fase', 'turno', 'mano_idx', 'triunfo', 'triunfo_propuesto',
        'carta_mesa', 'quien_va', 'votos_subasta', 'manos', 'baza_actual',
        'bazas_jugadas', 'puntos_mano', 'puntos_totales', 'cantes_ensenados',
        'jugables_humano', 'cantes_disponibles', 'cantes_anunciados_propios',
        'bolot_pendiente', 'dealer', 'objetivo', 'anuncios_primera')}


def serialize(estado):
    actor = estado.turno if estado.turno in HUMANS else 0
    result = estado.to_dict_para(actor)
    if estado.turno not in HUMANS:
        result['puede_ensenar_cantes'] = False
        result['cantes_disponibles'] = []
        result['cantes_anunciados_propios'] = []
        result['cantes_ensenados_propios'] = []
        result['cantes_pendientes_humano'] = []
        result['bolot_pendiente'] = None
    # The UI drives both human hands (J0 and J2): expose both face up and keep
    # AI hands as counts. Training observations still see a single private hand.
    result['manos'] = [[c.to_dict() for c in estado.manos[j]] if j in HUMANS
                       else len(estado.manos[j]) for j in range(4)]
    result['modo_testeo'] = True
    result['jugables_humano'] = ([c.to_dict() for c in cartas_jugables(estado, actor)]
                                  if estado.turno in HUMANS and estado.fase == Fase.BAZAS else [])
    if actor in HUMANS and estado.turno in HUMANS:
        pov = estado.to_dict_para(actor)
        for k in ('cantes_disponibles', 'cantes_anunciados_propios',
                  'cantes_ensenados_propios', 'bolot_pendiente'):
            result[k] = pov[k]
    return result


def enabled():
    return bool(os.environ.get('BOLOT_TESTEO_CODE') and
                os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_ROLE_KEY'))


def save(event):
    """Commit one event; reconcile an ambiguous POST against the exact saved row."""
    base = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/bolot_testeo_events'
    key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}
    payload = json.dumps(event, ensure_ascii=False).encode()
    url = base + '?on_conflict=game_id,seq'
    req = urllib.request.Request(url, payload, method='POST', headers={
        **headers, 'Content-Type': 'application/json', 'Prefer': 'return=minimal',
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError('Supabase no confirmó el registro')
            return
    except Exception as first_error:
        # A timeout may mean the row was written. Check the exact key, and
        # accept only an exact match, not a conflicting decision at the same seq.
        query = urllib.parse.urlencode({'game_id':'eq.' + event['game_id'],
                                         'seq':'eq.' + str(event['seq']), 'select':'*'})
        read = urllib.request.Request(base + '?' + query, headers=headers)
        try:
            with urllib.request.urlopen(read, timeout=8) as response:
                rows = json.load(response)
            if len(rows) == 1 and all(rows[0].get(k) == v for k,v in event.items()):
                return
        except Exception:
            pass
        raise RuntimeError('Supabase no confirmó esta decisión') from first_error


def event(before, after, actor, action, seq, hand_index):
    if action.get('type') == 'ai_step':
        if before.fase in (Fase.SUBASTA_PRIMERAS, Fase.SUBASTA_SEGUNDAS):
            action = {'type': 'bid', 'decision': 'voy' if after.quien_va == actor and after.fase == Fase.BAZAS else 'no_voy',
                      'suit': after.triunfo.value if after.quien_va == actor and after.triunfo else None}
        elif len(after.baza_actual.cartas) > len(before.baza_actual.cartas):
            action = {'type': 'play_card', 'card': after.baza_actual.cartas[-1][1].to_dict(),
                      'announced': [c.tipo for c in after.cantes_anunciados.get(actor, []) if c not in before.cantes_anunciados.get(actor, [])],
                      'bolot': after.bolot_declarado[actor] and not before.bolot_declarado[actor]}
        elif len(after.bazas_jugadas) > len(before.bazas_jugadas):
            played = next((c.to_dict() for j,c in after.bazas_jugadas[-1].cartas if j == actor), None)
            action = {'type':'play_card', 'card': played,
                      'announced': [c.tipo for c in after.cantes_anunciados.get(actor, []) if c not in before.cantes_anunciados.get(actor, [])],
                      'bolot': after.bolot_declarado[actor] and not before.bolot_declarado[actor]}
        elif len(after.cantes_ensenados.get(actor, [])) > len(before.cantes_ensenados.get(actor, [])):
            action = {'type':'reveal_declarations'}
        else:
            action = {'type':'ai_step_no_card'}
    return {'game_id': before.id, 'seq': seq, 'hand_index': hand_index,
            'actor': actor, 'actor_kind': 'human' if actor in HUMANS else 'ai',
            'phase': before.fase.value, 'observation': observation(before, actor),
            'action': action, 'result': {
                'phase': after.fase.value, 'turn': after.turno,
                'trick_winner': after.bazas_jugadas[-1].ganador if len(after.bazas_jugadas) > len(before.bazas_jugadas) else None,
                'trick_points': after.bazas_jugadas[-1].puntos if len(after.bazas_jugadas) > len(before.bazas_jugadas) else None,
                'points': list(after.puntos_mano), 'final_totals': list(after.puntos_totales) if after.fase == Fase.FIN_MANO else None,
            }}


