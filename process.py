import json
import glob
import os

# --- CONFIGURATION ---
MIN_LAPS_PERCENTAGE = 0.70 
OUTPUT_FILE = "dashboard_data.json"

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

def load_and_process():
    global_drivers = {} 
    session_list = [] 
    hall_of_fame = {}

    folders_to_check = [".", "session_results", "quali_results"]
    raw_files = []
    for folder in folders_to_check:
        raw_files.extend(glob.glob(os.path.join(folder, "*.json")))
        raw_files.extend(glob.glob(os.path.join(folder, "*.JSON")))

    unique_files = {os.path.realpath(f): f for f in raw_files}
    all_files = list(unique_files.values())
    all_files.sort(key=os.path.getmtime)

    qualy_sessions = []
    race_sessions = []

    for f in all_files:
        data = read_json(f)
        if not data or 'sessionResult' not in data: continue
        
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
                "qualy": {"time_ms": 2000000000, "driver": "-", "car": 0, "wet": 0},
                "race": {"time_ms": 2000000000, "driver": "-", "car": 0, "wet": 0}
            }

        qualy_dict = {}
        qualy_pole_ms = 2000000000
        
        q_data = None
        if track_name in qualy_sessions_by_track and len(qualy_sessions_by_track[track_name]) > 0:
            q_data = qualy_sessions_by_track[track_name].pop(0) 
        
        if q_data:
            q_leaderboard = q_data['sessionResult']['leaderBoardLines']
            q_is_wet = q_data['sessionResult'].get('isWetSession', 0)
            
            for line in q_leaderboard:
                bl = line['timing']['bestLap']
                if bl < 2000000000 and bl < qualy_pole_ms:
                    qualy_pole_ms = bl

            valid_q_pos = 1
            for line in q_leaderboard:
                pid = line['currentDriver']['playerId']
                q_time = line['timing']['bestLap']
                
                if q_time < 2000000000:
                    qualy_dict[pid] = {
                        "pos": valid_q_pos,
                        "time_ms": q_time,
                        "gap_ms": q_time - qualy_pole_ms if qualy_pole_ms < 2000000000 else 0
                    }
                    
                    if q_time < hall_of_fame[track_name]["qualy"]["time_ms"]:
                        hall_of_fame[track_name]["qualy"] = {
                            "time_ms": q_time,
                            "driver": f"{line['currentDriver']['firstName']} {line['currentDriver']['lastName']}".strip(),
                            "car": line['car']['carModel'],
                            "wet": q_is_wet
                        }
                    valid_q_pos += 1
        
        session_best_lap = 2000000000
        max_laps_session = 0

        for line in race_leaderboard:
            timing = line['timing']
            if timing['lapCount'] > max_laps_session:
                max_laps_session = timing['lapCount']
            if timing['bestLap'] < 2000000000 and timing['bestLap'] < session_best_lap:
                session_best_lap = timing['bestLap']

        min_laps_required = max_laps_session * MIN_LAPS_PERCENTAGE
        threshold_107 = session_best_lap * 1.07 if session_best_lap < 2000000000 else 0

        car_laps_data = {}
        for lap in race_data.get('laps', []):
            cid = lap['carId']
            ltime = lap['laptime']
            if cid not in car_laps_data:
                car_laps_data[cid] = {'valid_laps': [], 'incidents': 0, 'all_laps': []}
            
            if ltime < 2000000000:
                is_incident = threshold_107 > 0 and ltime > threshold_107
                if not is_incident:
                    car_laps_data[cid]['valid_laps'].append(ltime)
                else:
                    car_laps_data[cid]['incidents'] += 1
                
                car_laps_data[cid]['all_laps'].append({'time_ms': ltime, 'is_incident': is_incident})

        session_best_avg_pace = 2000000000
        for line in race_leaderboard:
            timing = line['timing']
            if timing['totalTime'] > 2000000000 or timing['lapCount'] < min_laps_required: continue

            car_id = line['car']['carId']
            valid_laps = car_laps_data.get(car_id, {}).get('valid_laps', [])
            if valid_laps:
                pace = sum(valid_laps) / len(valid_laps)
                if pace < session_best_avg_pace:
                    session_best_avg_pace = pace

        temp_drivers = []
        valid_pos_counter = 1 
        seen_pids = set()
        
        for line in race_leaderboard:
            timing = line['timing']
            driver = line['currentDriver']
            pid = driver['playerId']
            
            if pid in seen_pids: continue
            seen_pids.add(pid)
            
            name = f"{driver['firstName']} {driver['lastName']}".strip() 
            car_id = line['car']['carId']
            car_model = line['car']['carModel']
            
            laps = timing['lapCount']
            total_time = timing['totalTime']
            best_lap = timing['bestLap']

            is_classified = laps >= min_laps_required

            if is_classified:
                display_pos = valid_pos_counter
                real_pos_num = valid_pos_counter
                points = POINTS_SYSTEM.get(valid_pos_counter, 0)
                
                if best_lap < 2000000000 and best_lap < hall_of_fame[track_name]["race"]["time_ms"]:
                    hall_of_fame[track_name]["race"] = {
                        "time_ms": best_lap,
                        "driver": name,
                        "car": car_model,
                        "wet": race_is_wet
                    }
                valid_pos_counter += 1
            else:
                display_pos = "DNF"
                real_pos_num = -1
                points = 0

            valid_laps = car_laps_data.get(car_id, {}).get('valid_laps', [])
            incidents = car_laps_data.get(car_id, {}).get('incidents', "-") if is_classified else "-"
            
            avg_lap_driver_ms = sum(valid_laps) / len(valid_laps) if valid_laps and is_classified else None
            lap_history = car_laps_data.get(car_id, {}).get('all_laps', []) if is_classified else []
            
            gap_pace_str = "-"
            current_pace_gap_ms = 0
            has_valid_pace_gap = False
            if is_classified and avg_lap_driver_ms and session_best_avg_pace < 2000000000:
                diff = avg_lap_driver_ms - session_best_avg_pace
                gap_pace_str = f"+{diff/1000:.3f}" if diff > 0 else "PACE REF"
                current_pace_gap_ms = diff
                has_valid_pace_gap = True

            gap_best_str = "-"
            current_best_gap_ms = 0
            if is_classified and best_lap < 2000000000 and session_best_lap < 2000000000:
                diff = best_lap - session_best_lap
                gap_best_str = f"+{diff/1000:.3f}" if diff > 0 else "BEST LAP"
                current_best_gap_ms = diff

            q_info = qualy_dict.get(pid, None)
            q_pos = q_info['pos'] if q_info else "-"
            q_time_str = format_time(q_info['time_ms']) if q_info else "-"
            q_gap_ms = q_info['gap_ms'] if q_info else 0
            q_gap_str = "POLE" if q_info and q_gap_ms == 0 else (f"+{q_gap_ms/1000:.3f}" if q_info else "-")
            
            net_vs_q = q_pos - real_pos_num if is_classified and q_info and q_pos != "-" else "-"

            # --- Añadidos raw MS times para Personal Bests ---
            temp_drivers.append({
                "pid": pid, "is_classified": is_classified, "real_pos_num": real_pos_num, 
                "pos": display_pos, "qualy_pos": q_pos, "qualy_time": q_time_str,
                "qualy_time_ms": q_info['time_ms'] if q_info else None, # AÑADIDO
                "qualy_gap": q_gap_str, "qualy_gap_ms": q_gap_ms, "net_vs_q": net_vs_q,
                "name": name, "car_model": car_model, "points": points,
                "laps": laps if is_classified else "-", "incidents": incidents, 
                "avg_time": format_time(avg_lap_driver_ms) if is_classified else "-",
                "avg_lap_ms": avg_lap_driver_ms, "lap_history": lap_history, 
                "gap_pace_ms": current_pace_gap_ms, "gap_best_ms": current_best_gap_ms, 
                "has_valid_pace_gap": has_valid_pace_gap, "gap_pace": gap_pace_str,
                "best_lap": format_time(best_lap) if is_classified and best_lap < 2000000000 else "-",
                "best_lap_ms": best_lap if is_classified and best_lap < 2000000000 else None, # AÑADIDO
                "gap_best": gap_best_str
            })

        valid_paces = [d for d in temp_drivers if d['avg_lap_ms'] is not None and d['is_classified']]
        valid_paces.sort(key=lambda x: x['avg_lap_ms'])
        for i, d in enumerate(valid_paces): d['pace_pos'] = i + 1
        for d in temp_drivers:
            if 'pace_pos' not in d: d['pace_pos'] = "-"

        session_results = []
        qualy_results_export = [] 
        
        for d in temp_drivers:
            pid = d['pid']
            
            if pid not in global_drivers:
                global_drivers[pid] = {
                    "name": d['name'], "cars": {}, "total_points": 0, "races": 0,
                    "pos_sum": 0, "pos_count": 0, "pace_pos_sum": 0, "pace_pos_count": 0,
                    "pos_gained_vs_pace": 0, "gap_pace_sum_ms": 0, "gap_count": 0,
                    "qualy_pos_sum": 0, "qualy_pos_count": 0, 
                    "qualy_gap_sum_ms": 0, "qualy_gap_count": 0, "net_pos_gained_vs_qualy": 0
                }
            
            if d['is_classified']:
                global_drivers[pid]["cars"][d['car_model']] = global_drivers[pid]["cars"].get(d['car_model'], 0) + 1
                global_drivers[pid]["total_points"] += d['points']
                global_drivers[pid]["races"] += 1 
                global_drivers[pid]["pos_sum"] += d['real_pos_num']
                global_drivers[pid]["pos_count"] += 1
                
                if d['pace_pos'] != "-":
                    global_drivers[pid]["pos_gained_vs_pace"] += (d['pace_pos'] - d['real_pos_num'])
                    global_drivers[pid]["pace_pos_sum"] += d['pace_pos']
                    global_drivers[pid]["pace_pos_count"] += 1

                if d['has_valid_pace_gap'] and track_name != "nurburgring_24h":
                    global_drivers[pid]["gap_pace_sum_ms"] += d['gap_pace_ms']
                    global_drivers[pid]["gap_count"] += 1

                if d['qualy_pos'] != "-":
                    global_drivers[pid]["qualy_pos_sum"] += d['qualy_pos']
                    global_drivers[pid]["qualy_pos_count"] += 1
                    global_drivers[pid]["net_pos_gained_vs_qualy"] += d['net_vs_q']
                    
                    if track_name != "nurburgring_24h":
                        global_drivers[pid]["qualy_gap_sum_ms"] += d['qualy_gap_ms']
                        global_drivers[pid]["qualy_gap_count"] += 1

            if d['qualy_pos'] != "-":
                qualy_results_export.append({
                    "pos": d['qualy_pos'], "name": d['name'], "car_model": d['car_model'],
                    "best_lap": d['qualy_time'], "gap_pole": d['qualy_gap'], "gap_pole_ms": d['qualy_gap_ms']
                })

            del d['pid']
            del d['is_classified']
            del d['real_pos_num']
            del d['has_valid_pace_gap']
            session_results.append(d)

        qualy_results_export.sort(key=lambda x: x['pos'])

        session_list.append({
            "id": f"race_{file_index}",
            "name": f"Round {file_index + 1}: {track_name.replace('_', ' ').title()}",
            "results": session_results,
            "qualy_results": qualy_results_export 
        })

    final_ranking = []
    for pid, data in global_drivers.items():
        if data["races"] == 0 or data["pos_count"] == 0: continue

        avg_points = data["total_points"] / data["races"]
        avg_pos_str = round(data["pos_sum"] / data["pos_count"], 1) if data["pos_count"] > 0 else "-" 
        avg_pace_pos_str = round(data["pace_pos_sum"] / data["pace_pos_count"], 1) if data["pace_pos_count"] > 0 else "-"
        avg_gap_str = f"+{data['gap_pace_sum_ms']/data['gap_count']/1000:.3f}" if data["gap_count"] > 0 else "-"

        avg_q_pos_str = round(data["qualy_pos_sum"] / data["qualy_pos_count"], 1) if data["qualy_pos_count"] > 0 else "-" 
        avg_q_gap_str = f"+{data['qualy_gap_sum_ms']/data['qualy_gap_count']/1000:.3f}" if data["qualy_gap_count"] > 0 else "-"

        favorite_car_id = max(data["cars"], key=data["cars"].get) if data["cars"] else 0

        final_ranking.append({
            "name": data["name"],
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
        if record["qualy"]["time_ms"] == 2000000000: record["qualy"]["time_ms"] = None
        if record["race"]["time_ms"] == 2000000000: record["race"]["time_ms"] = None

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