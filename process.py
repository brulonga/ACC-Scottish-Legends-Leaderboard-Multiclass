import json
import glob
import os

# --- CONFIGURATION ---
JSON_FOLDER = "session_results"
OUTPUT_FILE = "dashboard_data.json"

MIN_LAPS_PERCENTAGE = 0.70 

POINTS_SYSTEM = {
    1: 180, 2: 150, 3: 120, 4: 105, 5: 96,
    6: 90, 7: 84, 8: 78, 9: 72, 10: 66,
    11: 60, 12: 57, 13: 54, 14: 51, 15: 48,
    16: 45, 17: 42, 18: 39, 19: 36, 20: 33,
    21: 30, 22: 27, 23: 27, 24: 21, 25: 18,
    26: 15, 27: 12, 28: 9, 29: 6, 30: 3
}

def format_time(ms):
    if ms is None or ms == 0 or ms > 2000000000: 
        return "-"
    minutes = int(ms // 60000)
    seconds = int((ms % 60000) // 1000)
    milis = int(ms % 1000)
    return f"{minutes}:{seconds:02d}.{milis:03d}"

def load_and_process():
    global_drivers = {} 
    session_list = [] 

    files = glob.glob(os.path.join(JSON_FOLDER, "*.json"))
    files.sort(key=os.path.getmtime) 

    for file_index, file_path in enumerate(files):
        data = None
        encodings = ['utf-8-sig', 'utf-16-le', 'utf-16', 'latin-1', 'cp1252']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    data = json.load(f)
                break 
            except (UnicodeError, json.JSONDecodeError, UnicodeDecodeError):
                continue

        if data is None or 'sessionResult' not in data:
            continue
            
        session_type = data.get('sessionType', 'R')
        if session_type not in ['R', 'R1', 'R2']: 
            continue

        track_name = data.get('trackName', 'Unknown Track')
        leaderboard = data['sessionResult']['leaderBoardLines']
        
        session_best_lap = float('inf')
        max_laps_session = 0

        for line in leaderboard:
            timing = line['timing']
            if timing['lapCount'] > max_laps_session:
                max_laps_session = timing['lapCount']
            if timing['bestLap'] < 2000000000 and timing['bestLap'] < session_best_lap:
                session_best_lap = timing['bestLap']

        min_laps_required = max_laps_session * MIN_LAPS_PERCENTAGE
        threshold_107 = session_best_lap * 1.07 if session_best_lap != float('inf') else 0

        car_laps_data = {}
        for lap in data.get('laps', []):
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
                
                car_laps_data[cid]['all_laps'].append({
                    'time_ms': ltime,
                    'is_incident': is_incident
                })

        session_best_avg_pace = float('inf')

        for line in leaderboard:
            timing = line['timing']
            if timing['totalTime'] > 2000000000: continue 
            if timing['lapCount'] < min_laps_required: continue

            car_id = line['car']['carId']
            valid_laps = car_laps_data.get(car_id, {}).get('valid_laps', [])
            
            if valid_laps:
                pace = sum(valid_laps) / len(valid_laps)
                if pace < session_best_avg_pace:
                    session_best_avg_pace = pace

        temp_drivers = []
        valid_pos_counter = 1 
        seen_pids = set()
        
        for line in leaderboard:
            timing = line['timing']
            driver = line['currentDriver']
            pid = driver['playerId']
            
            if pid in seen_pids:
                continue
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
                valid_pos_counter += 1
            else:
                display_pos = "DNF"
                real_pos_num = -1
                points = 0

            valid_laps = car_laps_data.get(car_id, {}).get('valid_laps', [])
            incidents = car_laps_data.get(car_id, {}).get('incidents', 0)
            
            avg_lap_driver_ms = sum(valid_laps) / len(valid_laps) if valid_laps and is_classified else None
            lap_history = car_laps_data.get(car_id, {}).get('all_laps', []) if is_classified else []
            
            gap_pace_str = "-"
            current_pace_gap_ms = 0
            has_valid_pace_gap = False

            if is_classified and avg_lap_driver_ms and session_best_avg_pace != float('inf'):
                diff = avg_lap_driver_ms - session_best_avg_pace
                gap_pace_str = f"+{diff/1000:.3f}" if diff > 0 else "PACE REF"
                current_pace_gap_ms = diff
                has_valid_pace_gap = True

            gap_best_str = "-"
            current_best_gap_ms = 0
            if is_classified and best_lap < 2000000000 and session_best_lap != float('inf'):
                diff = best_lap - session_best_lap
                gap_best_str = f"+{diff/1000:.3f}" if diff > 0 else "BEST LAP"
                current_best_gap_ms = diff

            temp_drivers.append({
                "pid": pid,
                "is_classified": is_classified,
                "real_pos_num": real_pos_num, 
                "pos": display_pos,
                "name": name,
                "car_model": car_model,
                "points": points,
                "laps": laps if is_classified else "-", 
                "incidents": incidents if is_classified else "-", 
                "avg_time": format_time(avg_lap_driver_ms) if is_classified else "-",
                "avg_lap_ms": avg_lap_driver_ms, 
                "lap_history": lap_history, 
                "gap_pace_ms": current_pace_gap_ms, 
                "gap_best_ms": current_best_gap_ms, 
                "has_valid_pace_gap": has_valid_pace_gap,
                "gap_pace": gap_pace_str,
                "best_lap": format_time(best_lap) if is_classified and best_lap < 2000000000 else "-",
                "gap_best": gap_best_str
            })

        valid_paces = [d for d in temp_drivers if d['avg_lap_ms'] is not None and d['is_classified']]
        valid_paces.sort(key=lambda x: x['avg_lap_ms'])
        
        for i, d in enumerate(valid_paces):
            d['pace_pos'] = i + 1

        for d in temp_drivers:
            if 'pace_pos' not in d:
                d['pace_pos'] = "-"

        session_results = []
        for d in temp_drivers:
            pid = d['pid']
            
            if pid not in global_drivers:
                global_drivers[pid] = {
                    "name": d['name'],
                    "cars": {}, 
                    "total_points": 0,
                    "races": 0,
                    "pos_sum": 0,
                    "pos_count": 0,
                    "pace_pos_sum": 0,
                    "pace_pos_count": 0,
                    "pos_gained_vs_pace": 0, 
                    "gap_pace_sum_ms": 0, 
                    "gap_count": 0 
                }
            
            # --- AQUÍ ESTÁ EL CAMBIO ---
            # Solo acumulamos la participación si el piloto se clasificó
            if d['is_classified']:
                global_drivers[pid]["cars"][d['car_model']] = global_drivers[pid]["cars"].get(d['car_model'], 0) + 1
                global_drivers[pid]["total_points"] += d['points']
                global_drivers[pid]["races"] += 1 
                global_drivers[pid]["pos_sum"] += d['real_pos_num']
                global_drivers[pid]["pos_count"] += 1
                
                if d['pace_pos'] != "-":
                    gained = d['pace_pos'] - d['real_pos_num']
                    global_drivers[pid]["pos_gained_vs_pace"] += gained
                
                if d['pace_pos'] != "-":
                    global_drivers[pid]["pace_pos_sum"] += d['pace_pos']
                    global_drivers[pid]["pace_pos_count"] += 1

                if d['has_valid_pace_gap'] and track_name != "nurburgring_24h":
                    global_drivers[pid]["gap_pace_sum_ms"] += d['gap_pace_ms']
                    global_drivers[pid]["gap_count"] += 1

            del d['pid']
            del d['is_classified']
            del d['real_pos_num']
            del d['has_valid_pace_gap']
            session_results.append(d)

        session_list.append({
            "id": f"race_{file_index}",
            "name": f"Round {file_index + 1}: {track_name.replace('_', ' ').title()}",
            "results": session_results
        })

    final_ranking = []
    for pid, data in global_drivers.items():
        # Si tiene 0 carreras (porque solo corrió en carreras donde hizo DNF), ni lo metemos
        if data["races"] == 0: continue 

        avg_points = data["total_points"] / data["races"]
        
        avg_pos_str = round(data["pos_sum"] / data["pos_count"], 1) if data["pos_count"] > 0 else "-" 
        avg_pace_pos_str = round(data["pace_pos_sum"] / data["pace_pos_count"], 1) if data["pace_pos_count"] > 0 else "-"

        if data["gap_count"] > 0:
            avg_gap_ms = data["gap_pace_sum_ms"] / data["gap_count"]
            avg_gap_str = f"+{avg_gap_ms/1000:.3f}"
        else:
            avg_gap_str = "-"

        favorite_car_id = max(data["cars"], key=data["cars"].get) if data["cars"] else 0

        final_ranking.append({
            "name": data["name"],
            "favorite_car": favorite_car_id,
            "points": data["total_points"],
            "avg_points": round(avg_points, 2),
            "avg_pos": avg_pos_str,
            "avg_pace_pos": avg_pace_pos_str,
            "net_pos_gained": data["pos_gained_vs_pace"],
            "avg_gap": avg_gap_str,
            "races": data["races"] 
        })
    
    final_ranking.sort(key=lambda x: (-x["points"], float(x["avg_gap"].replace('+', '')) if x["avg_gap"] != "-" else float('inf')))

    mega_json = {
        "global": final_ranking,
        "sessions": session_list
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(mega_json, f, indent=2)
    
    print(f"✅ Dashboard updated: {OUTPUT_FILE}")

if __name__ == "__main__":
    load_and_process()