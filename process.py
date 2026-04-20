import json
import glob
import os

# --- CONFIGURATION ---
MIN_LAPS_STATS = 0.50        # 50%: Mínimo para extraer telemetría y ritmo (pero no suma carrera ni puntos)
MIN_LAPS_CLASSIFIED = 0.85   # 90%: Mínimo para recibir puntos, contar como carrera terminada y afectar a la media
OUTPUT_FILE = "dashboard_data.json"

# --- SISTEMA DE SANCIONES ---
PENALTIES = {
    "nurburgring_24h": {
    },
    "brands_hatch": {
        "Málnási Dániel": 15,
        "Tommi Pommi": 5,
        "Gael Duchêne ESP [SL]": 5,
    }
}

POINTS_SYSTEM = {
    1: 180, 2: 150, 3: 120, 4: 105, 5: 96,
    6: 90, 7: 84, 8: 78, 9: 72, 10: 66,
    11: 60, 12: 57, 13: 54, 14: 51, 15: 48,
    16: 45, 17: 42, 18: 39, 19: 36, 20: 33,
    21: 30, 22: 27, 23: 27, 24: 21, 25: 18,
    26: 15, 27: 12, 28: 9, 29: 6, 30: 3
}

def format_time(ms):
    if ms is None or ms == 0 or ms >= 2000000000: 
        return "-"
    minutes = int(ms // 60000)
    seconds = int((ms % 60000) // 1000)
    milis = int(ms % 1000)
    return f"{minutes}:{seconds:02d}.{milis:03d}"

def read_json(file_path):
    encodings = ['utf-8-sig', 'utf-16-le', 'utf-16', 'latin-1', 'cp1252']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return json.load(f)
        except (UnicodeError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return None

def custom_sort_leaderboard(line):
    laps = line['timing']['lapCount']
    ttime = line['timing']['totalTime']
    return (-laps, ttime)

def load_and_process():
    global_drivers = {} 
    session_list = [] 
    hall_of_fame = {}

    folders_to_check = [".", "session_results", "qualy_results", "quali_results", "qualy", "quali"]
    raw_files = []
    for folder in folders_to_check:
        raw_files.extend(glob.glob(os.path.join(folder, "*.json")))
        raw_files.extend(glob.glob(os.path.join(folder, "*.JSON")))

    unique_files = {os.path.realpath(f): f for f in raw_files}
    all_files = list(unique_files.values())
    all_files.sort(key=os.path.getmtime)

    qualy_sessions = []
    race_sessions = []
    seen_fingerprints = set()

    for f in all_files:
        data = read_json(f)
        if not data or 'sessionResult' not in data: continue
        
        try:
            t_name = data.get('trackName', 'unknown')
            b_lap = data['sessionResult'].get('bestlap', 0)
            tot_laps = sum(line['timing']['lapCount'] for line in data['sessionResult']['leaderBoardLines'])
            fingerprint = f"{t_name}_{b_lap}_{tot_laps}"
        except:
            fingerprint = f

        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)

        session_type = data.get('sessionType', '').upper()
        if not session_type:
            if '_Q' in f.upper(): session_type = 'Q'
            elif '_R' in f.upper(): session_type = 'R'

        if session_type == 'Q':
            qualy_sessions.append(data)
        elif session_type in ['R', 'R1', 'R2']:
            race_sessions.append(data)

    qualy_sessions_by_track = {}
    for q_data in qualy_sessions:
        t_name = q_data.get('trackName', 'Unknown Track')
        if t_name not in qualy_sessions_by_track:
            qualy_sessions_by_track[t_name] = []
        qualy_sessions_by_track[t_name].append(q_data)

    for file_index, race_data in enumerate(race_sessions):
        track_name = race_data.get('trackName', 'Unknown Track')
        race_leaderboard = race_data['sessionResult']['leaderBoardLines']
        race_is_wet = race_data['sessionResult'].get('isWetSession', 0)

        if track_name not in hall_of_fame:
            hall_of_fame[track_name] = {
                "name": track_name.replace('_', ' ').title(),
                "GT3": {
                    "qualy": {"time_ms": 2000000000, "driver": "-", "car": 0, "wet": 0},
                    "race": {"time_ms": 2000000000, "driver": "-", "car": 0, "wet": 0}
                },
                "GT4": {
                    "qualy": {"time_ms": 2000000000, "driver": "-", "car": 0, "wet": 0},
                    "race": {"time_ms": 2000000000, "driver": "-", "car": 0, "wet": 0}
                }
            }

        # APLICAR PENALIZACIONES
        for line in race_leaderboard:
            driver_name = f"{line['currentDriver']['firstName']} {line['currentDriver']['lastName']}".strip()
            penalty_sec = PENALTIES.get(track_name, {}).get(driver_name, 0)
            
            ttime = line['timing']['totalTime']
            if penalty_sec > 0 and ttime > 0 and ttime < 2000000000:
                line['timing']['totalTime'] += (penalty_sec * 1000)
                line['penalty_applied'] = penalty_sec
            else:
                line['penalty_applied'] = 0

        race_leaderboard.sort(key=custom_sort_leaderboard)

        car_id_to_class = {}
        for line in race_leaderboard:
            cid = line['car']['carId']
            cgroup = line['car']['carGroup']
            car_id_to_class[cid] = "GT4" if cgroup == "GT4" else "GT3"

        qualy_dict = {}
        qualy_pole_ms = {"GT3": 2000000000, "GT4": 2000000000}
        
        q_data = None
        if track_name in qualy_sessions_by_track and len(qualy_sessions_by_track[track_name]) > 0:
            q_data = qualy_sessions_by_track[track_name].pop(0) 
        
        if q_data:
            q_leaderboard = q_data['sessionResult']['leaderBoardLines']
            q_is_wet = q_data['sessionResult'].get('isWetSession', 0)
            
            # --- EXTRAER SECTORES DE QUALY ---
            q_driver_cars = {}
            for line in q_leaderboard:
                d_name = f"{line['currentDriver']['firstName']} {line['currentDriver']['lastName']}".strip()
                cid = line['car']['carId']
                q_driver_cars[cid] = d_name

            q_best_laps_splits = {}
            for lap in q_data.get('laps', []):
                cid = lap['carId']
                d_name = q_driver_cars.get(cid)
                if not d_name: continue
                ltime = lap['laptime']
                splits = lap.get('splits', [])
                if ltime < 2000000000:
                    if d_name not in q_best_laps_splits or ltime < q_best_laps_splits[d_name]['laptime']:
                        q_best_laps_splits[d_name] = {'laptime': ltime, 'splits': splits}
            # ---------------------------------

            for line in q_leaderboard:
                c_class = "GT4" if line['car']['carGroup'] == "GT4" else "GT3"
                bl = line['timing']['bestLap']
                if bl < 2000000000 and bl < qualy_pole_ms[c_class]:
                    qualy_pole_ms[c_class] = bl

            valid_q_pos = {"GT3": 1, "GT4": 1}
            for line in q_leaderboard:
                c_class = "GT4" if line['car']['carGroup'] == "GT4" else "GT3"
                driver_name = f"{line['currentDriver']['firstName']} {line['currentDriver']['lastName']}".strip()
                q_time = line['timing']['bestLap']
                
                splits = q_best_laps_splits.get(driver_name, {}).get('splits', [])
                s1 = format_time(splits[0]) if len(splits) > 0 and splits[0] else "-"
                s2 = format_time(splits[1]) if len(splits) > 1 and splits[1] else "-"
                s3 = format_time(splits[2]) if len(splits) > 2 and splits[2] else "-"
                
                is_valid = q_time < 2000000000
                pos = valid_q_pos[c_class] if is_valid else "-"
                gap_ms = q_time - qualy_pole_ms[c_class] if is_valid and qualy_pole_ms[c_class] < 2000000000 else None

                qualy_dict[driver_name] = {
                    "pos": pos,
                    "time_ms": q_time if is_valid else None,
                    "gap_ms": gap_ms,
                    "s1": s1,
                    "s2": s2,
                    "s3": s3,
                    "car_model": line['car']['carModel'],
                    "car_class": c_class
                }
                
                if is_valid:
                    if q_time < hall_of_fame[track_name][c_class]["qualy"]["time_ms"]:
                        hall_of_fame[track_name][c_class]["qualy"] = {
                            "time_ms": q_time,
                            "driver": driver_name,
                            "car": line['car']['carModel'],
                            "wet": q_is_wet
                        }
                    valid_q_pos[c_class] += 1
        
        session_best_lap = {"GT3": 2000000000, "GT4": 2000000000}
        max_laps_session = {"GT3": 0, "GT4": 0}

        for line in race_leaderboard:
            c_class = "GT4" if line['car']['carGroup'] == "GT4" else "GT3"
            timing = line['timing']
            if timing['lapCount'] > max_laps_session[c_class]:
                max_laps_session[c_class] = timing['lapCount']
            if timing['bestLap'] < 2000000000 and timing['bestLap'] < session_best_lap[c_class]:
                session_best_lap[c_class] = timing['bestLap']

        # NUEVO: Doble sistema de porcentajes POR CLASE
        min_laps_stats = {
            "GT3": max_laps_session["GT3"] * MIN_LAPS_STATS,
            "GT4": max_laps_session["GT4"] * MIN_LAPS_STATS
        }
        min_laps_classified = {
            "GT3": max_laps_session["GT3"] * MIN_LAPS_CLASSIFIED,
            "GT4": max_laps_session["GT4"] * MIN_LAPS_CLASSIFIED
        }
        
        threshold_107 = {
            "GT3": session_best_lap["GT3"] * 1.07 if session_best_lap["GT3"] < 2000000000 else 0,
            "GT4": session_best_lap["GT4"] * 1.07 if session_best_lap["GT4"] < 2000000000 else 0
        }

        car_laps_data = {}
        for lap in race_data.get('laps', []):
            cid = lap['carId']
            ltime = lap['laptime']
            c_class = car_id_to_class.get(cid, "GT3")
            
            if cid not in car_laps_data:
                car_laps_data[cid] = {'valid_laps': [], 'incidents': 0, 'all_laps': []}
            
            if ltime < 2000000000:
                is_incident = threshold_107[c_class] > 0 and ltime > threshold_107[c_class]
                if not is_incident:
                    car_laps_data[cid]['valid_laps'].append(ltime)
                else:
                    car_laps_data[cid]['incidents'] += 1
                
                car_laps_data[cid]['all_laps'].append({'time_ms': ltime, 'is_incident': is_incident})

        session_best_avg_pace = {"GT3": 2000000000, "GT4": 2000000000}
        for line in race_leaderboard:
            c_class = "GT4" if line['car']['carGroup'] == "GT4" else "GT3"
            timing = line['timing']
            if timing['totalTime'] > 2000000000 or timing['lapCount'] < min_laps_stats[c_class]: continue

            car_id = line['car']['carId']
            valid_laps = car_laps_data.get(car_id, {}).get('valid_laps', [])
            if valid_laps:
                pace = sum(valid_laps) / len(valid_laps)
                if pace < session_best_avg_pace[c_class]:
                    session_best_avg_pace[c_class] = pace

        temp_drivers = []
        valid_pos_counter = {"GT3": 1, "GT4": 1}
        seen_pids = set()
        
        leader_laps = {"GT3": 0, "GT4": 0}
        leader_time = {"GT3": 0, "GT4": 0}

        for line in race_leaderboard:
            c_class = "GT4" if line['car']['carGroup'] == "GT4" else "GT3"
            timing = line['timing']
            driver = line['currentDriver']
            
            name = f"{driver['firstName']} {driver['lastName']}".strip() 
            pid = f"{name}::{c_class}" 
            
            if pid in seen_pids: continue
            seen_pids.add(pid)
            
            car_id = line['car']['carId']
            car_model = line['car']['carModel']
            
            laps = timing['lapCount']
            total_time = timing['totalTime']
            best_lap = timing['bestLap']
            penalty_applied = line.get('penalty_applied', 0)

            # APLICACIÓN DEL 90% Y EL 50%
            has_stats = laps >= min_laps_stats[c_class]
            gets_points = laps >= min_laps_classified[c_class]

            race_gap_str = "-"
            
            if gets_points:
                display_pos = valid_pos_counter[c_class]
                real_pos_num = valid_pos_counter[c_class]
                points = POINTS_SYSTEM.get(valid_pos_counter[c_class], 0)
                
                # CALCULAR RACE GAP
                if valid_pos_counter[c_class] == 1:
                    leader_laps[c_class] = laps
                    leader_time[c_class] = total_time
                    race_gap_str = "WINNER"
                else:
                    if laps == leader_laps[c_class]:
                        gap_ms = total_time - leader_time[c_class]
                        race_gap_str = f"+{gap_ms/1000:.3f}s"
                    else:
                        laps_behind = leader_laps[c_class] - laps
                        race_gap_str = f"+{laps_behind} Lap{'s' if laps_behind > 1 else ''}"

                if best_lap < 2000000000 and best_lap < hall_of_fame[track_name][c_class]["race"]["time_ms"]:
                    hall_of_fame[track_name][c_class]["race"] = {
                        "time_ms": best_lap,
                        "driver": name,
                        "car": car_model,
                        "wet": race_is_wet
                    }
                valid_pos_counter[c_class] += 1
            else:
                display_pos = "DNF"
                real_pos_num = -1
                points = 0
                if has_stats:
                    race_gap_str = "DNF"

            valid_laps = car_laps_data.get(car_id, {}).get('valid_laps', [])
            incidents = car_laps_data.get(car_id, {}).get('incidents', "-") if has_stats else "-"
            
            avg_lap_driver_ms = sum(valid_laps) / len(valid_laps) if valid_laps and has_stats else None
            lap_history = car_laps_data.get(car_id, {}).get('all_laps', []) 
            
            gap_pace_str = "-"
            current_pace_gap_ms = 0
            has_valid_pace_gap = False
            if has_stats and avg_lap_driver_ms and session_best_avg_pace[c_class] < 2000000000:
                diff = avg_lap_driver_ms - session_best_avg_pace[c_class]
                gap_pace_str = f"+{diff/1000:.3f}" if diff > 0 else "PACE REF"
                current_pace_gap_ms = diff
                has_valid_pace_gap = True

            gap_best_str = "-"
            current_best_gap_ms = 0
            if has_stats and best_lap < 2000000000 and session_best_lap[c_class] < 2000000000:
                diff = best_lap - session_best_lap[c_class]
                gap_best_str = f"+{diff/1000:.3f}" if diff > 0 else "BEST LAP"
                current_best_gap_ms = diff

            q_info = qualy_dict.get(name, None)
            q_pos = q_info['pos'] if q_info else "-"
            q_time_str = format_time(q_info['time_ms']) if q_info and q_info['time_ms'] else "-"
            q_gap_ms = q_info['gap_ms'] if q_info else None
            
            q_gap_str = "-"
            if q_info and q_gap_ms is not None:
                q_gap_str = "POLE" if q_gap_ms == 0 else f"+{q_gap_ms/1000:.3f}s"
            
            # Solo suma posiciones vs Qualy si terminaste la carrera recibiendo puntos
            net_vs_q = q_pos - real_pos_num if gets_points and q_pos != "-" else "-"

            # Se añaden TODOS los pilotos para que salgan en la tabla de carrera
            temp_drivers.append({
                "pid": pid, "car_class": c_class, "has_stats": has_stats, "gets_points": gets_points, 
                "real_pos_num": real_pos_num, "pos": display_pos, 
                "qualy_pos": q_pos, "qualy_time": q_time_str, "qualy_time_ms": q_info['time_ms'] if q_info else None, 
                "qualy_gap": q_gap_str, "qualy_gap_ms": q_gap_ms, "net_vs_q": net_vs_q,
                "name": name, "car_model": car_model, "points": points,
                "laps": laps, # Mostramos siempre las vueltas dadas
                "incidents": incidents, 
                "avg_time": format_time(avg_lap_driver_ms) if has_stats else "-",
                "avg_lap_ms": avg_lap_driver_ms, "lap_history": lap_history, 
                "gap_pace_ms": current_pace_gap_ms, "gap_best_ms": current_best_gap_ms, 
                "has_valid_pace_gap": has_valid_pace_gap, "gap_pace": gap_pace_str,
                "best_lap": format_time(best_lap) if has_stats and best_lap < 2000000000 else "-",
                "best_lap_ms": best_lap if has_stats and best_lap < 2000000000 else None,
                "gap_best": gap_best_str, "penalty": penalty_applied, "race_gap": race_gap_str
            })

        for cls in ["GT3", "GT4"]:
            valid_paces = [d for d in temp_drivers if d['avg_lap_ms'] is not None and d['has_stats'] and d['car_class'] == cls]
            valid_paces.sort(key=lambda x: x['avg_lap_ms'])
            for i, d in enumerate(valid_paces): d['pace_pos'] = i + 1
        
        for d in temp_drivers:
            if 'pace_pos' not in d: d['pace_pos'] = "-"

        session_results = []
        qualy_results_export = [] 
        
        # --- EXPORTACIÓN DE QUALY COMPLETA ---
        for d_name, q_info in qualy_dict.items():
            q_gap_str = "-"
            if q_info['gap_ms'] is not None:
                q_gap_str = "POLE" if q_info['gap_ms'] == 0 else f"+{q_info['gap_ms']/1000:.3f}s"
                
            qualy_results_export.append({
                "pos": q_info['pos'], 
                "name": d_name, 
                "car_class": q_info['car_class'],
                "car_model": q_info['car_model'], 
                "s1": q_info['s1'], 
                "s2": q_info['s2'], 
                "s3": q_info['s3'],
                "best_lap": format_time(q_info['time_ms']) if q_info['time_ms'] else "NO TIME", 
                "gap_pole": q_gap_str, 
                "gap_pole_ms": q_info['gap_ms']
            })

        def q_sort_key(x):
            p = x['pos']
            return (x['car_class'], p if isinstance(p, int) else 9999)
        
        qualy_results_export.sort(key=q_sort_key)
        # ------------------------------------------------------------------------

        for d in temp_drivers:
            pid = d['pid']
            c_class = d['car_class']
            
            if not d['has_stats']: 
                # Solo limpiamos variables internas antes de guardar
                d_export = d.copy()
                del d_export['pid']
                del d_export['has_stats']
                del d_export['gets_points']
                del d_export['real_pos_num']
                del d_export['has_valid_pace_gap']
                session_results.append(d_export)
                continue 
            
            if pid not in global_drivers:
                global_drivers[pid] = {
                    "name": d['name'], "car_class": c_class, "cars": {}, 
                    "total_points": 0, "races": 0, "pos_sum": 0, "pos_count": 0, 
                    "pace_pos_sum": 0, "pace_pos_count": 0, "pos_gained_vs_pace": 0, 
                    "gap_pace_sum_ms": 0, "gap_count": 0, "qualy_pos_sum": 0, 
                    "qualy_pos_count": 0, "qualy_gap_sum_ms": 0, "qualy_gap_count": 0, 
                    "net_pos_gained_vs_qualy": 0
                }
            
            global_drivers[pid]["cars"][d['car_model']] = global_drivers[pid]["cars"].get(d['car_model'], 0) + 1
            
            # SOLO SUMAMOS PUNTOS Y MEDIAS SI TERMINÓ DE VERDAD (90%)
            if d['gets_points']:
                global_drivers[pid]["races"] += 1 
                global_drivers[pid]["total_points"] += d['points']
                global_drivers[pid]["pos_sum"] += d['real_pos_num']
                global_drivers[pid]["pos_count"] += 1
                
                if d['pace_pos'] != "-":
                    global_drivers[pid]["pos_gained_vs_pace"] += (d['pace_pos'] - d['real_pos_num'])

            # Ritmo y Qualy se suman si tiene estadísticas (50%), aunque abandonara
            if d['pace_pos'] != "-":
                global_drivers[pid]["pace_pos_sum"] += d['pace_pos']
                global_drivers[pid]["pace_pos_count"] += 1

            if d['has_valid_pace_gap'] and track_name != "nurburgring_24h":
                global_drivers[pid]["gap_pace_sum_ms"] += d['gap_pace_ms']
                global_drivers[pid]["gap_count"] += 1

            if d['qualy_pos'] != "-":
                global_drivers[pid]["qualy_pos_sum"] += d['qualy_pos']
                global_drivers[pid]["qualy_pos_count"] += 1
                
                if d['gets_points'] and d['net_vs_q'] != "-":
                    global_drivers[pid]["net_pos_gained_vs_qualy"] += d['net_vs_q']
                
                if track_name != "nurburgring_24h" and d['qualy_gap_ms'] is not None:
                    global_drivers[pid]["qualy_gap_sum_ms"] += d['qualy_gap_ms']
                    global_drivers[pid]["qualy_gap_count"] += 1

            d_export = d.copy()
            del d_export['pid']
            del d_export['has_stats']
            del d_export['gets_points']
            del d_export['real_pos_num']
            del d_export['has_valid_pace_gap']
            session_results.append(d_export)

        session_list.append({
            "id": f"race_{file_index}",
            "name": f"Round {file_index + 1}: {track_name.replace('_', ' ').title()}",
            "results": session_results,
            "qualy_results": qualy_results_export 
        })

    final_ranking = []
    for pid, data in global_drivers.items():
        if data["pace_pos_count"] == 0 and data["qualy_pos_count"] == 0 and data["races"] == 0: 
            continue

        avg_points = data["total_points"] / data["races"] if data["races"] > 0 else 0
        avg_pos_str = round(data["pos_sum"] / data["pos_count"], 1) if data["pos_count"] > 0 else "-" 
        avg_pace_pos_str = round(data["pace_pos_sum"] / data["pace_pos_count"], 1) if data["pace_pos_count"] > 0 else "-"
        avg_gap_str = f"+{data['gap_pace_sum_ms']/data['gap_count']/1000:.3f}" if data["gap_count"] > 0 else "-"

        avg_q_pos_str = round(data["qualy_pos_sum"] / data["qualy_pos_count"], 1) if data["qualy_pos_count"] > 0 else "-" 
        avg_q_gap_str = f"+{data['qualy_gap_sum_ms']/data['qualy_gap_count']/1000:.3f}" if data["qualy_gap_count"] > 0 else "-"

        favorite_car_id = max(data["cars"], key=data["cars"].get) if data["cars"] else 0

        final_ranking.append({
            "name": data["name"],
            "car_class": data["car_class"], 
            "favorite_car": favorite_car_id,
            "points": data["total_points"],
            "avg_points": round(avg_points, 2),
            "avg_pos": avg_pos_str,
            "avg_pace_pos": avg_pace_pos_str,
            "net_pos_gained": data["pos_gained_vs_pace"],
            "avg_qualy_pos": avg_q_pos_str,
            "avg_qualy_gap": avg_q_gap_str,
            "net_pos_gained_qualy": data["net_pos_gained_vs_qualy"],
            "avg_gap": avg_gap_str,
            "races": data["races"] 
        })
    
    final_ranking.sort(key=lambda x: (-x["points"], float(x["avg_gap"].replace('+', '')) if x["avg_gap"] != "-" else 2000000000))

    for track, record in hall_of_fame.items():
        for cls in ["GT3", "GT4"]:
            if record[cls]["qualy"]["time_ms"] == 2000000000: record[cls]["qualy"]["time_ms"] = None
            if record[cls]["race"]["time_ms"] == 2000000000: record[cls]["race"]["time_ms"] = None

    mega_json = {
        "global": final_ranking,
        "sessions": session_list,
        "hall_of_fame": hall_of_fame 
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(mega_json, f, indent=2)
    
    print(f"✅ Dashboard updated: {OUTPUT_FILE}")

if __name__ == "__main__":
    load_and_process()