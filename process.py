import json
import glob
import os

# --- CONFIGURATION ---
JSON_FOLDER = "session_results"
OUTPUT_FILE = "dashboard_data.json"

# Minimum Laps Percentage to be classified (e.g. 0.50 = 50% of leader's laps)
MIN_LAPS_PERCENTAGE = 0.50 

POINTS_SYSTEM = {
    1: 180, 2: 150, 3: 120, 4: 105, 5: 96,
    6: 90, 7: 84, 8: 78, 9: 72, 10: 66,
    11: 60, 12: 57, 13: 54, 14: 51, 15: 48,
    16: 45, 17: 42, 18: 39, 19: 36, 20: 33,
    21: 30, 22: 27, 23: 27, 24: 21, 25: 18,
    26: 15, 27: 12, 28: 9, 29: 6, 30: 3
}

def format_time(ms):
    """Converts milliseconds to mm:ss.ms"""
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
        # 1. Robust File Reading
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
            print(f"⚠️ Warning: Skipping {os.path.basename(file_path)}")
            continue

        track_name = data.get('trackName', 'Unknown Track')
        leaderboard = data['sessionResult']['leaderBoardLines']
        
        # --- 2. SESSION ANALYSIS ---
        session_best_lap = float('inf')
        max_laps_session = 0

        # Find max laps done by the winner & Absolute Best Lap of the session
        for line in leaderboard:
            timing = line['timing']
            if timing['lapCount'] > max_laps_session:
                max_laps_session = timing['lapCount']
            
            if timing['bestLap'] < 2000000000 and timing['bestLap'] < session_best_lap:
                session_best_lap = timing['bestLap']

        min_laps_required = max_laps_session * MIN_LAPS_PERCENTAGE
        threshold_107 = session_best_lap * 1.07 if session_best_lap != float('inf') else 0

        # Process individual laps for 107% pace rule and incident counting
        car_laps_data = {}
        for lap in data.get('laps', []):
            cid = lap['carId']
            ltime = lap['laptime']
            if cid not in car_laps_data:
                car_laps_data[cid] = {'valid_laps': [], 'incidents': 0}
            
            if ltime < 2000000000:
                if threshold_107 > 0 and ltime <= threshold_107:
                    car_laps_data[cid]['valid_laps'].append(ltime)
                else:
                    car_laps_data[cid]['incidents'] += 1

        session_best_avg_pace = float('inf')

        # Find session records (Best Pace inside 107%)
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

        # --- 3. PROCESS DRIVERS ---
        session_results = []
        valid_pos_counter = 1 
        
        for line in leaderboard:
            timing = line['timing']
            driver = line['currentDriver']
            pid = driver['playerId']
            name = f"{driver['firstName']} {driver['lastName']}".strip() 
            car_id = line['car']['carId']
            car_model = line['car']['carModel']
            
            laps = timing['lapCount']
            total_time = timing['totalTime']
            best_lap = timing['bestLap']

            # --- FILTERS ---
            if total_time > 2000000000 or total_time == 0: continue 
            if laps < min_laps_required: continue
            # ---------------

            pos = valid_pos_counter
            valid_pos_counter += 1
            points = POINTS_SYSTEM.get(pos, 0)
            
            # Get valid laps and incidents for this driver
            valid_laps = car_laps_data.get(car_id, {}).get('valid_laps', [])
            incidents = car_laps_data.get(car_id, {}).get('incidents', 0)
            
            # Calculate 107% Filtered Avg Lap
            avg_lap_driver = sum(valid_laps) / len(valid_laps) if valid_laps else None
            
            # Calculate Pace Gap (RITMO) para la media global
            gap_pace_str = "-"
            current_pace_gap_ms = 0
            has_valid_pace_gap = False

            if avg_lap_driver and session_best_avg_pace != float('inf'):
                diff = avg_lap_driver - session_best_avg_pace
                gap_pace_str = f"+{diff/1000:.3f}" if diff > 0 else "PACE REF"
                current_pace_gap_ms = diff
                has_valid_pace_gap = True

            # Calculate Best Lap Gap (Solo para mostrar en la carrera)
            gap_best_str = "-"
            if best_lap < 2000000000 and session_best_lap != float('inf'):
                diff = best_lap - session_best_lap
                gap_best_str = f"+{diff/1000:.3f}" if diff > 0 else "BEST LAP"
            elif best_lap > 2000000000:
                best_lap = 0 # Format as "-"

            session_results.append({
                "pos": pos,
                "name": name,
                "car_model": car_model,
                "points": points,
                "laps": laps,
                "incidents": incidents,
                "avg_time": format_time(avg_lap_driver),
                "gap_pace": gap_pace_str,
                "best_lap": format_time(best_lap),
                "gap_best": gap_best_str
            })

            # --- GLOBAL ACCUMULATION ---
            if pid not in global_drivers:
                global_drivers[pid] = {
                    "name": name,
                    "total_points": 0,
                    "races": 0,
                    "pos_sum": 0,
                    "gap_pace_sum_ms": 0, # Ahora acumulamos el Pace Gap
                    "gap_count": 0 
                }
            
            global_drivers[pid]["name"] = name
            global_drivers[pid]["total_points"] += points
            global_drivers[pid]["races"] += 1
            global_drivers[pid]["pos_sum"] += pos
            
            # Sumar el Pace Gap para la tabla general (Excluyendo Nordschleife)
            if has_valid_pace_gap and track_name != "nurburgring_24h":
                global_drivers[pid]["gap_pace_sum_ms"] += current_pace_gap_ms
                global_drivers[pid]["gap_count"] += 1

        session_list.append({
            "id": f"race_{file_index}",
            "name": f"Round {file_index + 1}: {track_name.replace('_', ' ').title()}",
            "results": session_results
        })

    # 4. FINAL RANKING
    final_ranking = []
    for pid, data in global_drivers.items():
        if data["races"] == 0: continue

        avg_points = data["total_points"] / data["races"]
        avg_pos = data["pos_sum"] / data["races"]
        
        # Calcular el Avg Gap basándonos en el Pace
        if data["gap_count"] > 0:
            avg_gap_ms = data["gap_pace_sum_ms"] / data["gap_count"]
            avg_gap_str = f"+{avg_gap_ms/1000:.3f}"
        else:
            avg_gap_str = "-"

        final_ranking.append({
            "name": data["name"],
            "points": data["total_points"],
            "avg_points": round(avg_points, 2),
            "avg_pos": round(avg_pos, 1),
            "avg_gap": avg_gap_str,
            "races": data["races"]
        })
    
    # Ordenar por puntos (descendente) y luego por Pace Gap (ascendente) en caso de empate
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