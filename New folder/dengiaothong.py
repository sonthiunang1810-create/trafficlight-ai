import random
import time
import json
import os
from datetime import datetime
import threading
import http.server
import socketserver
import webbrowser

# ==============================
# ⚙️ CẤU HÌNH NÂNG CAO
# ==============================
CONFIG = {
    "LANE1_MAX": 15,
    "LANE2_MAX": 15,
    "LANE3_MAX": 15,
    "LANE4_MAX": 15,
    "EMERGENCY_PROB": 0.15,
    "POLICE_PROB": 0.08,
    "FIRE_PROB": 0.07,
    "LIGHT_MIN": 8,
    "LIGHT_MAX": 15,
    "YELLOW_MIN": 3,
    "YELLOW_MAX": 5,
    "MAX_CYCLES": 10,
    "SCALE_FACTOR": 1.2,
    "LOG_FILE": "traffic_log.txt",
    "CAR_SPEED_NORMAL": 8,
    "CAR_SPEED_EMERGENCY": 15,
    "CAR_SPEED_SLOW": 5,
    "MAX_CARS_PER_LANE": 8,
    "CAR_SPAWN_PROB": 0.3
}

HTML_FILE = "traffic_simulation.html"

# ==============================
# 📜 HỆ THỐNG LOG NÂNG CAO
# ==============================
class TrafficLogger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.entries = []
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        print(log_entry)
        
        # Thêm vào bộ nhớ
        self.entries.append(log_entry)
        
        # Ghi vào file
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
        
        return log_entry
    
    def get_recent_logs(self, count=15):
        return self.entries[-count:] if self.entries else []

# Khởi tạo logger
logger = TrafficLogger(CONFIG["LOG_FILE"])

# ==============================
# 🚗 LỚP XE NÂNG CAO
# ==============================
class Car:
    CAR_TYPES = {
        "normal": {"emoji": "🚗", "speed": CONFIG["CAR_SPEED_NORMAL"], "priority": 0},
        "emergency": {"emoji": "🚑", "speed": CONFIG["CAR_SPEED_EMERGENCY"], "priority": 3},
        "police": {"emoji": "🚓", "speed": CONFIG["CAR_SPEED_EMERGENCY"], "priority": 2},
        "fire": {"emoji": "🚒", "speed": CONFIG["CAR_SPEED_EMERGENCY"], "priority": 1},
        "truck": {"emoji": "🚚", "speed": CONFIG["CAR_SPEED_SLOW"], "priority": 0},
        "bus": {"emoji": "🚌", "speed": CONFIG["CAR_SPEED_SLOW"], "priority": 0}
    }
    
    def __init__(self, lane, car_type="normal"):
        self.lane = lane
        self.type = car_type
        self.position = random.randint(-100, -20)  # Xuất hiện từ ngoài màn hình
        self.speed = self.CAR_TYPES[car_type]["speed"]
        self.priority = self.CAR_TYPES[car_type]["priority"]
        self.emoji = self.CAR_TYPES[car_type]["emoji"]
        self.waiting_time = 0
        self.passed = False
        
    def move(self, light_state, priority_active):
        # Xe ưu tiên luôn di chuyển bất kể đèn giao thông
        if self.priority > 0 and priority_active:
            self.position += self.speed + 5  # Tăng tốc khi có ưu tiên
# Xe thường chỉ di chuyển khi đèn xanh hoặc vàng
        elif light_state == "green":
            self.position += self.speed
        elif light_state == "yellow":
            self.position += self.speed * 0.7  # Giảm tốc khi đèn vàng
        elif light_state == "red":
            # Đèn đỏ - xe dừng lại
            self.waiting_time += 1
            # Chỉ cho phép di chuyển nếu đã vượt quá vạch dừng (position > 350)
            if self.position < 350:  # Vạch dừng ở giữa đường
                self.position += 0  # Dừng hoàn toàn
            else:
                self.position += self.speed * 0.3  # Đi chậm nếu đã vượt vạch
        
        # Reset xe khi ra khỏi màn hình
        if self.position > 900:
            self.position = random.randint(-200, -50)
            self.passed = True
            self.waiting_time = 0
            
    def get_display_info(self):
        return {
            "lane": self.lane,
            "type": self.type,
            "position": self.position,
            "emoji": self.emoji,
            "waiting_time": self.waiting_time
        }

# ==============================
# 🚦 LỚP ĐÈN GIAO THÔNG THÔNG MINH
# ==============================
class SmartTrafficLight:
    def __init__(self):
        self.state = "red"
        self.timer = 0
        self.start_time = time.time()
        self.priority_active = False
        self.priority_type = "none"
        self.priority_end_time = 0
        self.cycle_count = 0
        self.total_vehicles_passed = 0
        
    def set_state(self, state, duration):
        self.state = state
        self.timer = duration
        self.start_time = time.time()
        logger.log(f"Đèn chuyển sang {state.upper()} trong {duration} giây")
        
    def time_left(self):
        elapsed = time.time() - self.start_time
        return max(0, self.timer - elapsed)
    
    def is_done(self):
        return self.time_left() <= 0
    
    def activate_priority(self, priority_type, duration=10):
        self.priority_active = True
        self.priority_type = priority_type
        self.priority_end_time = time.time() + duration
        logger.log(f"🚨 Kích hoạt ưu tiên: {priority_type.upper()} trong {duration} giây", "PRIORITY")
    
    def update_priority(self):
        if self.priority_active and time.time() > self.priority_end_time:
            self.priority_active = False
            self.priority_type = "none"
            logger.log("Kết thúc chế độ ưu tiên", "PRIORITY")
    
    def increment_cycle(self):
        self.cycle_count += 1
    
    def vehicle_passed(self):
        self.total_vehicles_passed += 1

# ==============================
# 🧠 HỆ THỐNG AI CẢM BIẾN THÔNG MINH
# ==============================
class TrafficAISensor:
    def __init__(self):
        self.history = []
        self.priority_vehicles_detected = 0
        
    def scan_traffic(self, cars, current_cycle):
# Phân tích mật độ xe theo làn
        lane_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        emergency_vehicles = []
        
        for car in cars:
            lane_counts[car.lane] += 1
            if car.priority > 0 and not car.passed:
                emergency_vehicles.append(car)
        
        # Xác định phương tiện ưu tiên
        priority_type = "none"
        if emergency_vehicles:
            highest_priority = max(emergency_vehicles, key=lambda x: x.priority)
            priority_type = highest_priority.type
            self.priority_vehicles_detected += 1
        
        # Tính toán mật độ tổng thể
        total_vehicles = sum(lane_counts.values())
        
        # Phân tích lịch sử để dự đoán
        self.history.append({
            "cycle": current_cycle,
            "lane_counts": lane_counts.copy(),
            "total": total_vehicles,
            "priority": priority_type,
            "timestamp": time.time()
        })
        
        # Giữ lịch sử tối đa 10 cycles
        if len(self.history) > 10:
            self.history.pop(0)
        
        # Tạo báo cáo
        density_level = "RẤT ÍT" if total_vehicles < 5 else "ÍT" if total_vehicles < 10 else "TRUNG BÌNH" if total_vehicles < 15 else "NHIỀU" if total_vehicles < 20 else "RẤT NHIỀU"
        
        logger.log(f"AI Scan: L1={lane_counts[0]}, L2={lane_counts[1]}, L3={lane_counts[2]}, L4={lane_counts[3]}, "
                  f"Tổng={total_vehicles} ({density_level}), Ưu tiên={priority_type}")
        
        return {
            "lane_counts": lane_counts,
            "total": total_vehicles,
            "priority": priority_type,
            "density_level": density_level,
            "emergency_count": len(emergency_vehicles)
        }

# ==============================
# 🧮 THUẬT TOÁN QUYẾT ĐỊNH THỜI GIAN ĐÈN
# ==============================
class LightDecisionAlgorithm:
    def __init__(self):
        self.base_times = {
            "red": CONFIG["LIGHT_MIN"],
            "green": CONFIG["LIGHT_MIN"], 
            "yellow": CONFIG["YELLOW_MIN"]
        }
    
    def calculate_light_times(self, traffic_data, current_cycle):
        priority = traffic_data["priority"]
        total_vehicles = traffic_data["total"]
        lane_counts = traffic_data["lane_counts"]
        
        # ƯU TIÊN CAO: Xe khẩn cấp
        if priority != "none":
            red_time = 15  # Thời gian đỏ ngắn
            green_time = min(23, CONFIG["LIGHT_MAX"] + 2)  # Thời gian xanh dài hơn
            yellow_time = CONFIG["YELLOW_MAX"]
            logger.log(f"Chế độ ưu tiên: Đỏ={red_time}s, Xanh={green_time}s", "PRIORITY")
            return red_time, green_time, yellow_time
        
        # ĐIỀU CHỈNH THEO MẬT ĐỘ
        base_green = CONFIG["LIGHT_MIN"]
        
        if total_vehicles > 15:
            green_time = min(CONFIG["LIGHT_MAX"], base_green + 8)
        elif total_vehicles > 10:
            green_time = min(CONFIG["LIGHT_MAX"], base_green + 5)
        elif total_vehicles > 5:
            green_time = min(CONFIG["LIGHT_MAX"], base_green + 3)
        else:
            green_time = base_green
        
        # Điều chỉnh theo chu kỳ
        if current_cycle > 5:
            green_time = min(green_time + 2, CONFIG["LIGHT_MAX"])
        
        red_time = max(CONFIG["LIGHT_MIN"], green_time - 2)
        yellow_time = random.randint(CONFIG["YELLOW_MIN"], CONFIG["YELLOW_MAX"])
        
        logger.log(f"Điều chỉnh đèn: Đỏ={red_time}s, Xanh={green_time}s, Vàng={yellow_time}s")
        return red_time, green_time, yellow_time

# ==============================
# 🛣️ LỚP QUẢN LÝ GIAO THÔNG
# ==============================
class TrafficManager:
    def __init__(self):
        self.cars = []
        self.light = SmartTrafficLight()
        self.sensor = TrafficAISensor()
        self.decision_algorithm = LightDecisionAlgorithm()
        self.last_spawn_time = time.time()
        self.spawn_interval = 2  # giây
        
    def spawn_cars(self):
        current_time = time.time()
        if current_time - self.last_spawn_time < self.spawn_interval:
            return
        
        self.last_spawn_time = current_time
        
        # Kiểm tra số lượng xe hiện tại
        current_car_count = len(self.cars)
        if current_car_count >= CONFIG["MAX_CARS_PER_LANE"] * 4:
            return
        
        # Xác suất sinh xe mới
        if random.random() < CONFIG["CAR_SPAWN_PROB"]:
            lane = random.randint(0, 3)
            
            # Xác định loại xe
            rand_val = random.random()
            if rand_val < CONFIG["EMERGENCY_PROB"]:
                car_type = "emergency"
            elif rand_val < CONFIG["EMERGENCY_PROB"] + CONFIG["POLICE_PROB"]:
                car_type = "police" 
            elif rand_val < CONFIG["EMERGENCY_PROB"] + CONFIG["POLICE_PROB"] + CONFIG["FIRE_PROB"]:
                car_type = "fire"
            elif rand_val < 0.8:  # 30% còn lại cho xe thường
                car_type = random.choice(["normal", "truck", "bus"])
            else:
                car_type = "normal"
            
            new_car = Car(lane, car_type)
            self.cars.append(new_car)
    
    def update_cars(self):
        # Di chuyển tất cả xe
        for car in self.cars:
            car.move(self.light.state, self.light.priority_active)
            
            # Đếm xe đã qua
            if car.position > 800 and not car.passed:
                car.passed = True
                self.light.vehicle_passed()
        
        # Loại bỏ xe đã ra khỏi màn hình quá lâu
        self.cars = [car for car in self.cars if car.position < 900 or not car.passed]
    
    def run_cycle(self, cycle_number):
        logger.log(f"🚦 Bắt đầu chu kỳ {cycle_number}", "CYCLE")
        
        # Quét giao thông
        traffic_data = self.sensor.scan_traffic(self.cars, cycle_number)
        
        # Quyết định thời gian đèn
        red_time, green_time, yellow_time = self.decision_algorithm.calculate_light_times(
            traffic_data, cycle_number
        )
        
        # Kích hoạt ưu tiên nếu có
        if traffic_data["priority"] != "none":
            self.light.activate_priority(traffic_data["priority"], green_time + 2)
        
        # Chu kỳ đèn: ĐỎ -> XANH -> VÀNG
        light_sequence = [
            ("red", red_time),
            ("green", green_time), 
            ("yellow", yellow_time)
        ]
        
        for state, duration in light_sequence:
            self.light.set_state(state, duration)
            
            start_state_time = time.time()
            while time.time() - start_state_time < duration:
                # Cập nhật trạng thái ưu tiên
                self.light.update_priority()
                
                # Sinh xe mới
                self.spawn_cars()
                
                # Cập nhật vị trí xe
                self.update_cars()
                
                # Ghi dữ liệu JSON
                self.write_simulation_data(cycle_number)
                
                time.sleep(0.5)  # 2 FPS
            
            logger.log(f"Kết thúc {state.upper()} chu kỳ {cycle_number}")
        
        self.light.increment_cycle()
    
    def write_simulation_data(self, current_cycle):
        data = {
            "light_state": self.light.state,
            "cars": [car.get_display_info() for car in self.cars],
            "current_cycle": current_cycle,
            "max_cycles": CONFIG["MAX_CYCLES"],
            "remaining_time": self.light.time_left(),
            "priority_type": self.light.priority_type,
            "priority_active": self.light.priority_active,
            "total_vehicles_passed": self.light.total_vehicles_passed,
            "log": logger.get_recent_logs(10)
        }
        
        with open("traffic_data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

# ==============================
# 🌐 GIAO DIỆN WEB NÂNG CAO
# ==============================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚦 Hệ Thống Đèn Giao Thông Thông Minh AI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }
        
        header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 3px solid #eee;
        }
        
        h1 {
            color: #2c3e50;
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        .subtitle {
            color: #7f8c8d;
            font-size: 1.2em;
            font-weight: 300;
        }
        
        .simulation-area {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }
        
        @media (max-width: 768px) {
            .simulation-area {
                grid-template-columns: 1fr;
            }
        }
        
        .traffic-canvas-container {
            background: #2c3e50;
            border-radius: 15px;
            padding: 20px;
            box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.3);
        }
        
        #trafficCanvas {
            width: 100%;
            height: 500px;
            background: #34495e;
            border-radius: 10px;
            display: block;
        }
        
        .control-panel {
            background: #ecf0f1;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .stat-card {
            background: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #2c3e50;
            margin: 5px 0;
        }
        
        .stat-label {
            font-size: 0.9em;
            color: #7f8c8d;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .light-indicator {
            text-align: center;
            margin: 20px 0;
            padding: 20px;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }
        
        .light-state {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
            text-transform: uppercase;
        }
        
        .state-red { color: #e74c3c; }
.state-green { color: #27ae60; }
        .state-yellow { color: #f39c12; }
        
        .timer {
            font-size: 3em;
            font-weight: bold;
            color: #2c3e50;
            margin: 10px 0;
        }
        
        .priority-alert {
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            margin: 15px 0;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .log-container {
            background: #2c3e50;
            border-radius: 15px;
            padding: 20px;
            color: white;
        }
        
        #log {
            height: 200px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            line-height: 1.4;
            background: #1a252f;
            padding: 15px;
            border-radius: 10px;
            margin-top: 10px;
        }
        
        .log-entry {
            margin-bottom: 5px;
            padding: 3px 0;
            border-bottom: 1px solid #34495e;
        }
        
        .log-time {
            color: #3498db;
        }
        
        .log-priority {
            color: #e74c3c;
            font-weight: bold;
        }
        
        .lane-info {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            font-size: 0.8em;
            color: #bdc3c7;
        }
        
        .road-markings {
            position: absolute;
            width: 100%;
            height: 100%;
            pointer-events: none;
        }
        
        .road-line {
            position: absolute;
            background: white;
            opacity: 0.8;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚦 Hệ Thống Đèn Giao Thông Thông Minh AI</h1>
            <div class="subtitle">Edge Computing & Artificial Intelligence trong quản lý giao thông đô thị</div>
        </header>
        
        <div class="simulation-area">
            <div class="traffic-canvas-container">
                <canvas id="trafficCanvas" width="800" height="500"></canvas>
            </div>
            
            <div class="control-panel">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">Chu Kỳ Hiện Tại</div>
                        <div class="stat-value" id="cycle">1</div>
                        <div class="stat-label">/<span id="maxCycle">10</span></div>
                    </div>
                    
                    <div class="stat-card">
<div class="stat-label">Xe Đã Qua</div>
                        <div class="stat-value" id="vehiclesPassed">0</div>
                        <div class="stat-label">Phương Tiện</div>
                    </div>
                </div>
                
                <div class="light-indicator">
                    <div class="stat-label">Trạng Thái Đèn</div>
                    <div class="light-state" id="stateDisplay">ĐỎ</div>
                    <div class="timer" id="timer">0.0s</div>
                    <div class="stat-label">Thời Gian Còn Lại</div>
                </div>
                
                <div id="priorityDisplay" style="display: none;">
                    <div class="priority-alert">
                        <div style="font-size: 1.5em;">🚨 ƯU TIÊN KHẨN CẤP</div>
                        <div id="priorityType" style="font-size: 1.2em; margin-top: 5px;"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="log-container">
            <div style="display: flex; justify-content: between; align-items: center; margin-bottom: 10px;">
                <h3 style="color: white;">📋 Nhật Ký Hệ Thống</h3>
                <button onclick="clearLog()" style="background: #e74c3c; color: white; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer;">Xóa Log</button>
            </div>
            <div id="log"></div>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('trafficCanvas');
        const ctx = canvas.getContext('2d');
        
        // Kích thước thực tế của canvas
        const canvasWidth = 800;
        const canvasHeight = 500;
        
        // Thiết lập kích thước hiển thị
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        
        // Biến toàn cục
        let simulationData = {};
        
        // Vẽ đường và làn xe
        function drawRoad() {
            // Mặt đường
            ctx.fillStyle = '#34495e';
            ctx.fillRect(0, 0, canvasWidth, canvasHeight);
            
            // Vẽ vạch kẻ đường giữa (loại bỏ vạch trên cùng)
            ctx.strokeStyle = 'white';
            ctx.lineWidth = 2;
            ctx.setLineDash([10, 15]);
            
            // Chỉ vẽ 2 vạch phân cách giữa các làn (thay vì 3)
            for (let i = 1; i <= 2; i++) {
                const y = (canvasHeight / 3) * i;
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvasWidth, y);
                ctx.stroke();
            }
            
            ctx.setLineDash([]);
            
            // Vẽ vạch dừng
            ctx.strokeStyle = 'white';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(350, 0);
            ctx.lineTo(350, canvasHeight);
            ctx.stroke();
// Vẽ biển báo dừng
            ctx.fillStyle = 'red';
            ctx.font = '12px Arial';
            ctx.fillText('VẠCH DỪNG', 360, canvasHeight / 2);
        }
        
        // Vẽ đèn giao thông
        function drawTrafficLight(state) {
            const lightX = 700;
            const lightY = 50;
            const lightWidth = 80;
            const lightHeight = 200;
            
            // Thân đèn
            ctx.fillStyle = '#2c3e50';
            ctx.fillRect(lightX, lightY, lightWidth, lightHeight);
            ctx.fillStyle = '#34495e';
            ctx.fillRect(lightX - 10, lightY + lightHeight, 100, 20);
            
            // Đèn
            const lights = [
                { color: '#e74c3c', state: 'red', y: lightY + 20 },
                { color: '#f39c12', state: 'yellow', y: lightY + 80 },
                { color: '#27ae60', state: 'green', y: lightY + 140 }
            ];
            
            lights.forEach(light => {
                ctx.beginPath();
                ctx.arc(lightX + lightWidth/2, light.y, 25, 0, Math.PI * 2);
                ctx.fillStyle = light.state === state ? light.color : '#7f8c8d';
                ctx.fill();
                ctx.strokeStyle = '#2c3e50';
                ctx.lineWidth = 2;
                ctx.stroke();
            });
        }
        
        // Vẽ xe
        function drawCars(cars) {
            cars.forEach(car => {
                const x = car.position;
                const laneHeight = canvasHeight / 4;
                const y = 50 + (car.lane * laneHeight);
                
                // Vẽ xe bằng emoji
                ctx.font = '30px Arial';
                ctx.fillText(car.emoji, x, y);
                
                // Hiển thị thời gian chờ nếu xe đang dừng
                if (car.waiting_time > 30) {
                    ctx.fillStyle = 'red';
                    ctx.font = '12px Arial';
                    ctx.fillText(`${car.waiting_time}s`, x, y - 10);
                }
            });
        }
        
        // Cập nhật giao diện
        function updateDisplay(data) {
            document.getElementById('cycle').textContent = data.current_cycle;
            document.getElementById('maxCycle').textContent = data.max_cycles;
            document.getElementById('vehiclesPassed').textContent = data.total_vehicles_passed || 0;
            
            // Cập nhật trạng thái đèn
            const stateDisplay = document.getElementById('stateDisplay');
            stateDisplay.textContent = data.light_state.toUpperCase();
            stateDisplay.className = 'light-state state-' + data.light_state;
            
            // Cập nhật timer
            document.getElementById('timer').textContent = data.remaining_time.toFixed(1) + 's';
            
            // Cập nhật ưu tiên
            const priorityDisplay = document.getElementById('priorityDisplay');
if (data.priority_active) {
                priorityDisplay.style.display = 'block';
                document.getElementById('priorityType').textContent = 
                    data.priority_type.toUpperCase() + ' ƯU TIÊN';
            } else {
                priorityDisplay.style.display = 'none';
            }
            
            // Cập nhật log
            const logElement = document.getElementById('log');
            logElement.innerHTML = data.log.map(entry => 
                `<div class="log-entry"><span class="log-time">${entry.substring(1, 9)}</span> ${entry.substring(12)}</div>`
            ).join('');
            logElement.scrollTop = logElement.scrollHeight;
        }
        
        // Vẽ toàn bộ cảnh
        function drawScene(data) {
            // Xóa canvas
            ctx.clearRect(0, 0, canvasWidth, canvasHeight);
            
            // Vẽ các thành phần
            drawRoad();
            drawTrafficLight(data.light_state);
            drawCars(data.cars);
        }
        
        // Lấy dữ liệu từ server
        async function fetchData() {
            try {
                const response = await fetch('traffic_data.json?t=' + new Date().getTime());
                simulationData = await response.json();
                updateDisplay(simulationData);
                drawScene(simulationData);
            } catch (error) {
                console.error('Lỗi khi tải dữ liệu:', error);
            }
        }
        
        // Xóa log
        function clearLog() {
            const logElement = document.getElementById('log');
            logElement.innerHTML = '';
        }
        
        // Bắt đầu cập nhật
        setInterval(fetchData, 500);
        fetchData();
    </script>
</body>
</html>"""

# ==============================
# 🕹️ WEB SERVER
# ==============================
class TrafficHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Tắt log mặc định của HTTP server
        pass

def start_web_server():
    # Tạo file HTML
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    
    # Khởi động server
    PORT = 8000
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    with socketserver.TCPServer(("", PORT), TrafficHTTPRequestHandler) as httpd:
        print(f"🌐 Server đang chạy tại: http://localhost:{PORT}")
        print("🔄 Đang khởi động mô phỏng giao thông...")
        webbrowser.open(f"http://localhost:{PORT}/{HTML_FILE}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n⏹️ Dừng server...")

# ==============================
# 🚀 CHƯƠNG TRÌNH CHÍNH
# ==============================
def main():
    print("=" * 60)
    print("🚦 HỆ THỐNG ĐÈN GIAO THÔNG THÔNG MINH AI")
    print("   Sử dụng Edge Computing & Artificial Intelligence")
print("=" * 60)
    
    # Xóa log cũ
if os.path.exists(CONFIG["LOG_FILE"]):
        os.remove(CONFIG["LOG_FILE"])
    
    # Khởi tạo hệ thống
        traffic_manager = TrafficManager()
    
def run_simulation():
        logger.log("🎬 Bắt đầu mô phỏng hệ thống đèn giao thông thông minh", "SYSTEM")
        
        try:
            for cycle in range(1, CONFIG["MAX_CYCLES"] + 1):
                traffic_manager.run_cycle(cycle)
                
                # Nghỉ giữa các chu kỳ
                if cycle < CONFIG["MAX_CYCLES"]:
                    time.sleep(2)
            
            logger.log("✅ Mô phỏng hoàn tất! Tổng số xe đã qua: " + 
                      str(traffic_manager.light.total_vehicles_passed), "SYSTEM")
                      
        except Exception as e:
            logger.log(f"❌ Lỗi trong mô phỏng: {str(e)}", "ERROR")
    
    # Chạy mô phỏng trong thread riêng
sim_thread = threading.Thread(target=run_simulation, daemon=True)
sim_thread.start()
    
    # Khởi động web server
start_web_server()


if __name__ == "__main__":
    main()
import random
import time
import json
import os
from datetime import datetime
import threading
import http.server
import socketserver
import webbrowser

# ==============================
# ⚙️ CẤU HÌNH NÂNG CAO
# ==============================
CONFIG = {
    "LANE1_MAX": 15,
    "LANE2_MAX": 15,
    "LANE3_MAX": 15,
    "LANE4_MAX": 15,
    "EMERGENCY_PROB": 0.15,
    "POLICE_PROB": 0.08,
    "FIRE_PROB": 0.07,
    "LIGHT_MIN": 8,
    "LIGHT_MAX": 15,
    "YELLOW_MIN": 3,
    "YELLOW_MAX": 5,
    "MAX_CYCLES": 10,
    "SCALE_FACTOR": 1.2,
    "LOG_FILE": "traffic_log.txt",
    "CAR_SPEED_NORMAL": 8,
    "CAR_SPEED_EMERGENCY": 15,
    "CAR_SPEED_SLOW": 5,
    "MAX_CARS_PER_LANE": 8,
    "CAR_SPAWN_PROB": 0.3
}

HTML_FILE = "traffic_simulation.html"

# ==============================
# 📜 HỆ THỐNG LOG NÂNG CAO
# ==============================
class TrafficLogger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.entries = []
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        print(log_entry)
        
        # Thêm vào bộ nhớ
        self.entries.append(log_entry)
        
        # Ghi vào file
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
        
        return log_entry
    
    def get_recent_logs(self, count=15):
        return self.entries[-count:] if self.entries else []

# Khởi tạo logger
logger = TrafficLogger(CONFIG["LOG_FILE"])

# ==============================
# 🚗 LỚP XE NÂNG CAO
# ==============================
class Car:
    CAR_TYPES = {
        "normal": {"emoji": "🚘", "speed": CONFIG["CAR_SPEED_NORMAL"], "priority": 0},
"emergency": {"emoji": "🚑", "speed": CONFIG["CAR_SPEED_EMERGENCY"], "priority": 3},
        "police": {"emoji": "🚓", "speed": CONFIG["CAR_SPEED_EMERGENCY"], "priority": 2},
        "fire": {"emoji": "🚒", "speed": CONFIG["CAR_SPEED_EMERGENCY"], "priority": 1},
        "truck": {"emoji": "🚚", "speed": CONFIG["CAR_SPEED_SLOW"], "priority": 0},
        "bus": {"emoji": "🚌", "speed": CONFIG["CAR_SPEED_SLOW"], "priority": 0}
    }
    
    def __init__(self, lane, car_type="normal"):
        self.lane = lane
        self.type = car_type
        self.position = random.randint(-100, -20)  # Xuất hiện từ ngoài màn hình
        self.speed = self.CAR_TYPES[car_type]["speed"]
        self.priority = self.CAR_TYPES[car_type]["priority"]
        self.emoji = self.CAR_TYPES[car_type]["emoji"]
        self.waiting_time = 0
        self.passed = False
        
    def move(self, light_state, priority_active):
        # Xe ưu tiên luôn di chuyển bất kể đèn giao thông
        if self.priority > 0 and priority_active:
            self.position += self.speed + 5  # Tăng tốc khi có ưu tiên
        # Xe thường chỉ di chuyển khi đèn xanh hoặc vàng
        elif light_state == "green":
            self.position += self.speed
        elif light_state == "yellow":
            self.position += self.speed * 0.7  # Giảm tốc khi đèn vàng
        elif light_state == "red":
            # Đèn đỏ - xe dừng lại
            self.waiting_time += 1
            # Chỉ cho phép di chuyển nếu đã vượt quá vạch dừng (position > 350)
            if self.position < 350:  # Vạch dừng ở giữa đường
                self.position += 0  # Dừng hoàn toàn
            else:
                self.position += self.speed * 0.3  # Đi chậm nếu đã vượt vạch
        
        # Reset xe khi ra khỏi màn hình
        if self.position > 900:
            self.position = random.randint(-200, -50)
            self.passed = True
            self.waiting_time = 0
            
    def get_display_info(self):
        return {
            "lane": self.lane,
            "type": self.type,
            "position": self.position,
            "emoji": self.emoji,
            "waiting_time": self.waiting_time
        }

# ==============================
# 🚦 LỚP ĐÈN GIAO THÔNG THÔNG MINH
# ==============================
class SmartTrafficLight:
    def __init__(self):
        self.state = "red"
        self.timer = 0
        self.start_time = time.time()
        self.priority_active = False
        self.priority_type = "none"
        self.priority_end_time = 0
        self.cycle_count = 0
        self.total_vehicles_passed = 0
        
    def set_state(self, state, duration):
        self.state = state
        self.timer = duration
        self.start_time = time.time()
        logger.log(f"Đèn chuyển sang {state.upper()} trong {duration} giây")
        
    def time_left(self):
        elapsed = time.time() - self.start_time
        return max(0, self.timer - elapsed)
    
    def is_done(self):
        return self.time_left() <= 0
    
    def activate_priority(self, priority_type, duration=10):
        self.priority_active = True
        self.priority_type = priority_type
        self.priority_end_time = time.time() + duration
        logger.log(f"🚨 Kích hoạt ưu tiên: {priority_type.upper()} trong {duration} giây", "PRIORITY")
    
    def update_priority(self):
        if self.priority_active and time.time() > self.priority_end_time:
            self.priority_active = False
            self.priority_type = "none"
            logger.log("Kết thúc chế độ ưu tiên", "PRIORITY")
    
    def increment_cycle(self):
        self.cycle_count += 1
    
    def vehicle_passed(self):
        self.total_vehicles_passed += 1

# ==============================
# 🧠 HỆ THỐNG AI CẢM BIẾN THÔNG MINH
# ==============================
class TrafficAISensor:
    def __init__(self):
        self.history = []
        self.priority_vehicles_detected = 0
        
    def scan_traffic(self, cars, current_cycle):
        # Phân tích mật độ xe theo làn
        lane_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        emergency_vehicles = []
        
        for car in cars:
            lane_counts[car.lane] += 1
            if car.priority > 0 and not car.passed:
                emergency_vehicles.append(car)
        
        # Xác định phương tiện ưu tiên
        priority_type = "none"
        if emergency_vehicles:
            highest_priority = max(emergency_vehicles, key=lambda x: x.priority)
            priority_type = highest_priority.type
            self.priority_vehicles_detected += 1
        
        # Tính toán mật độ tổng thể
        total_vehicles = sum(lane_counts.values())
        
        # Phân tích lịch sử để dự đoán
        self.history.append({
            "cycle": current_cycle,
            "lane_counts": lane_counts.copy(),
            "total": total_vehicles,
            "priority": priority_type,
            "timestamp": time.time()
        })
        
        # Giữ lịch sử tối đa 10 cycles
        if len(self.history) > 10:
            self.history.pop(0)
        
        # Tạo báo cáo
        density_level = "RẤT ÍT" if total_vehicles < 5 else "ÍT" if total_vehicles < 10 else "TRUNG BÌNH" if total_vehicles < 15 else "NHIỀU" if total_vehicles < 20 else "RẤT NHIỀU"
        
        logger.log(f"AI Scan: L1={lane_counts[0]}, L2={lane_counts[1]}, L3={lane_counts[2]}, L4={lane_counts[3]}, "
                  f"Tổng={total_vehicles} ({density_level}), Ưu tiên={priority_type}")
        
        return {
            "lane_counts": lane_counts,
            "total": total_vehicles,
            "priority": priority_type,
            "density_level": density_level,
            "emergency_count": len(emergency_vehicles)
        }

# ==============================
# 🧮 THUẬT TOÁN QUYẾT ĐỊNH THỜI GIAN ĐÈN
# ==============================
class LightDecisionAlgorithm:
    def __init__(self):
        self.base_times = {
            "red": CONFIG["LIGHT_MIN"],
            "green": CONFIG["LIGHT_MIN"], 
            "yellow": CONFIG["YELLOW_MIN"]
        }
    
    def calculate_light_times(self, traffic_data, current_cycle):
        priority = traffic_data["priority"]
        total_vehicles = traffic_data["total"]
        lane_counts = traffic_data["lane_counts"]
        
        # ƯU TIÊN CAO: Xe khẩn cấp
        if priority != "none":
            red_time = 2  # Thời gian đỏ ngắn
            green_time = min(12, CONFIG["LIGHT_MAX"] + 2)  # Thời gian xanh dài hơn
            yellow_time = CONFIG["YELLOW_MAX"]
            logger.log(f"Chế độ ưu tiên: Đỏ={red_time}s, Xanh={green_time}s", "PRIORITY")
            return red_time, green_time, yellow_time
        
        # ĐIỀU CHỈNH THEO MẬT ĐỘ
        base_green = CONFIG["LIGHT_MIN"]
        
        if total_vehicles > 15:
            green_time = min(CONFIG["LIGHT_MAX"], base_green + 8)
        elif total_vehicles > 10:
            green_time = min(CONFIG["LIGHT_MAX"], base_green + 5)
        elif total_vehicles > 5:
            green_time = min(CONFIG["LIGHT_MAX"], base_green + 3)
        else:
            green_time = base_green
        
        # Điều chỉnh theo chu kỳ
        if current_cycle > 5:
            green_time = min(green_time + 2, CONFIG["LIGHT_MAX"])
        
        red_time = max(CONFIG["LIGHT_MIN"], green_time - 2)
        yellow_time = random.randint(CONFIG["YELLOW_MIN"], CONFIG["YELLOW_MAX"])
        
        logger.log(f"Điều chỉnh đèn: Đỏ={red_time}s, Xanh={green_time}s, Vàng={yellow_time}s")
        return red_time, green_time, yellow_time

# ==============================
# 🛣️ LỚP QUẢN LÝ GIAO THÔNG
# ==============================
class TrafficManager:
    def __init__(self):
        self.cars = []
        self.light = SmartTrafficLight()
        self.sensor = TrafficAISensor()
        self.decision_algorithm = LightDecisionAlgorithm()
        self.last_spawn_time = time.time()
        self.spawn_interval = 2  # giây
        
    def spawn_cars(self):
        current_time = time.time()
        if current_time - self.last_spawn_time < self.spawn_interval:
            return
        
        self.last_spawn_time = current_time
        
        # Kiểm tra số lượng xe hiện tại
        current_car_count = len(self.cars)
        if current_car_count >= CONFIG["MAX_CARS_PER_LANE"] * 4:
            return
        
        # Xác suất sinh xe mới
        if random.random() < CONFIG["CAR_SPAWN_PROB"]:
            lane = random.randint(0, 3)
            
            # Xác định loại xe
            rand_val = random.random()
            if rand_val < CONFIG["EMERGENCY_PROB"]:
                car_type = "emergency"
            elif rand_val < CONFIG["EMERGENCY_PROB"] + CONFIG["POLICE_PROB"]:
                    car_type = "police" 
            elif rand_val < CONFIG["EMERGENCY_PROB"] + CONFIG["POLICE_PROB"] + CONFIG["FIRE_PROB"]:
                car_type = "fire"
            elif rand_val < 0.8:  # 30% còn lại cho xe thường
                car_type = random.choice(["normal", "truck", "bus"])
            else: 
                car_type = "normal"
            
            new_car = Car(lane, car_type)
            self.cars.append(new_car)
    
    def update_cars(self):
        # Di chuyển tất cả xe
        for car in self.cars:
            car.move(self.light.state, self.light.priority_active)
            
            # Đếm xe đã qua
            if car.position > 800 and not car.passed:
                car.passed = True
                self.light.vehicle_passed()
        
        # Loại bỏ xe đã ra khỏi màn hình quá lâu
        self.cars = [car for car in self.cars if car.position < 900 or not car.passed]
    
    def run_cycle(self, cycle_number):
        logger.log(f"🚦 Bắt đầu chu kỳ {cycle_number}", "CYCLE")
        
        # Quét giao thông
        traffic_data = self.sensor.scan_traffic(self.cars, cycle_number)
        
        # Quyết định thời gian đèn
        red_time, green_time, yellow_time = self.decision_algorithm.calculate_light_times(
            traffic_data, cycle_number
        )
        
        # Kích hoạt ưu tiên nếu có
        if traffic_data["priority"] != "none":
            self.light.activate_priority(traffic_data["priority"], green_time + 2)
        
        # Chu kỳ đèn: ĐỎ -> XANH -> VÀNG
        light_sequence = [
            ("red", red_time),
            ("green", green_time), 
            ("yellow", yellow_time)
        ]
        
        for state, duration in light_sequence:
            self.light.set_state(state, duration)
            
            start_state_time = time.time()
            while time.time() - start_state_time < duration:
                # Cập nhật trạng thái ưu tiên
                self.light.update_priority()
                
                # Sinh xe mới
                self.spawn_cars()
                
                # Cập nhật vị trí xe
                self.update_cars()
                
                # Ghi dữ liệu JSON
                self.write_simulation_data(cycle_number)
                
                time.sleep(0.5)  # 2 FPS
            
            logger.log(f"Kết thúc {state.upper()} chu kỳ {cycle_number}")
        
        self.light.increment_cycle()
    
        def write_simulation_data(self, current_cycle):data = {
            "light_state": self.light.state,
            "cars": [car.get_display_info() for car in self.cars],
            "current_cycle": current_cycle,
            "max_cycles": CONFIG["MAX_CYCLES"],
            "remaining_time": self.light.time_left(),
            "priority_type": self.light.priority_type,
            "priority_active": self.light.priority_active,
"total_vehicles_passed": self.light.total_vehicles_passed,
            "log": logger.get_recent_logs(10)
        }
        
        with open("traffic_data.json", "w", encoding="utf-8") as f: 
            json.dump(data, f, indent=2, ensure_ascii=False)

# ==============================
# 🌐 GIAO DIỆN WEB NÂNG CAO
# ==============================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚦 Hệ Thống Đèn Giao Thông Thông Minh AI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(10px);
        }
        
        header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 3px solid #eee;
        }
        
        h1 {
            color: #2c3e50;
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        .subtitle {
            color: #7f8c8d;
            font-size: 1.2em;
            font-weight: 300;
        }
        
        .simulation-area {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }
        
        @media (max-width: 768px) {
            .simulation-area {
                grid-template-columns: 1fr;
            }
        }
        
        .traffic-canvas-container {
            background: #2c3e50;
            border-radius: 15px;
            padding: 20px;
            box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.3);
        }
        
        #trafficCanvas {
            width: 100%;
            height: 500px;
            background: #34495e;
            border-radius: 10px;
            display: block;
        }
        
        .control-panel {
            background: #ecf0f1;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .stat-card {
            background: white;
            padding: 15px;
border-radius: 10px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08);
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #2c3e50;
            margin: 5px 0;
        }
        
        .stat-label {
            font-size: 0.9em;
            color: #7f8c8d;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .light-indicator {
            text-align: center;
            margin: 20px 0;
            padding: 20px;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }
        
        .light-state {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
            text-transform: uppercase;
        }
        
        .state-red { color: #e74c3c; }
        .state-green { color: #27ae60; }
        .state-yellow { color: #f39c12; }
        
        .timer {
            font-size: 3em;
            font-weight: bold;
            color: #2c3e50;
            margin: 10px 0;
        }
        
        .priority-alert {
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            margin: 15px 0;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .log-container {
            background: #2c3e50;
            border-radius: 15px;
            padding: 20px;
            color: white;
        }
        
        #log {
            height: 200px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            line-height: 1.4;
            background: #1a252f;
            padding: 15px;
            border-radius: 10px;
            margin-top: 10px;
        }
        
        .log-entry {
            margin-bottom: 5px;
            padding: 3px 0;
            border-bottom: 1px solid #34495e;
        }
        
        .log-time {
            color: #3498db;
        }
        
        .log-priority {
            color: #e74c3c;
            font-weight: bold;
        }
        
        .lane-info {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            font-size: 0.8em;
            color: #bdc3c7;
        }
        
        .road-markings {
            position: absolute;
            width: 100%;
            height: 100%;
            pointer-events: none;
        }
.road-line {
            position: absolute;
            background: white;
            opacity: 0.8;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚦 Hệ Thống Đèn Giao Thông Thông Minh AI</h1>
            <div class="subtitle">Edge Computing & Artificial Intelligence trong quản lý giao thông đô thị</div>
        </header>
        
        <div class="simulation-area">
            <div class="traffic-canvas-container">
                <canvas id="trafficCanvas" width="800" height="500"></canvas>
            </div>
            
            <div class="control-panel">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">Chu Kỳ Hiện Tại</div>
                        <div class="stat-value" id="cycle">1</div>
                        <div class="stat-label">/<span id="maxCycle">10</span></div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-label">Xe Đã Qua</div>
                        <div class="stat-value" id="vehiclesPassed">0</div>
                        <div class="stat-label">Phương Tiện</div>
                    </div>
                </div>
                
                <div class="light-indicator">
                    <div class="stat-label">Trạng Thái Đèn</div>
                    <div class="light-state" id="stateDisplay">ĐỎ</div>
                    <div class="timer" id="timer">0.0s</div>
                    <div class="stat-label">Thời Gian Còn Lại</div>
                </div>
                
                <div id="priorityDisplay" style="display: none;">
                    <div class="priority-alert">
                        <div style="font-size: 1.5em;">🚨 ƯU TIÊN KHẨN CẤP</div>
                        <div id="priorityType" style="font-size: 1.2em; margin-top: 5px;"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="log-container">
            <div style="display: flex; justify-content: between; align-items: center; margin-bottom: 10px;">
                <h3 style="color: white;">📋 Nhật Ký Hệ Thống</h3>
                <button onclick="clearLog()" style="background: #e74c3c; color: white; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer;">Xóa Log</button>
            </div>
            <div id="log"></div>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('trafficCanvas');
        const ctx = canvas.getContext('2d');
        
        // Kích thước thực tế của canvas
        const canvasWidth = 800;
        const canvasHeight = 500;
        
        // Thiết lập kích thước hiển thị
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
// Biến toàn cục
        let simulationData = {};
        
        // Vẽ đường và làn xe
        function drawRoad() {
            // Mặt đường
            ctx.fillStyle = '#34495e';
            ctx.fillRect(0, 0, canvasWidth, canvasHeight);
            
            // Vẽ vạch kẻ đường giữa (loại bỏ vạch trên cùng)
            ctx.strokeStyle = 'white';
            ctx.lineWidth = 2;
            ctx.setLineDash([10, 15]);
            
            // Chỉ vẽ 2 vạch phân cách giữa các làn (thay vì 3)
            for (let i = 1; i <= 2; i++) {
                const y = (canvasHeight / 3) * i;
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(canvasWidth, y);
                ctx.stroke();
            }
            
            ctx.setLineDash([]);
            
            // Vẽ vạch dừng
            ctx.strokeStyle = 'white';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(350, 0);
            ctx.lineTo(350, canvasHeight);
            ctx.stroke();
            
            // Vẽ biển báo dừng
            ctx.fillStyle = 'red';
            ctx.font = '12px Arial';
            ctx.fillText('VẠCH DỪNG', 360, canvasHeight / 2);
        }
        
        // Vẽ đèn giao thông
        function drawTrafficLight(state) {
            const lightX = 700;
            const lightY = 50;
            const lightWidth = 80;
            const lightHeight = 200;
            
            // Thân đèn
            ctx.fillStyle = '#2c3e50';
            ctx.fillRect(lightX, lightY, lightWidth, lightHeight);
            ctx.fillStyle = '#34495e';
            ctx.fillRect(lightX - 10, lightY + lightHeight, 100, 20);
            
            // Đèn
            const lights = [
                { color: '#e74c3c', state: 'red', y: lightY + 20 },
                { color: '#f39c12', state: 'yellow', y: lightY + 80 },
                { color: '#27ae60', state: 'green', y: lightY + 140 }
            ];
            
            lights.forEach(light => {
                ctx.beginPath();
                ctx.arc(lightX + lightWidth/2, light.y, 25, 0, Math.PI * 2);
                ctx.fillStyle = light.state === state ? light.color : '#7f8c8d';
                ctx.fill();
                ctx.strokeStyle = '#2c3e50';
                ctx.lineWidth = 2;
                ctx.stroke();
            });
        }
        
        // Vẽ xe
        function drawCars(cars) {
            cars.forEach(car => {
                const x = car.position;
                const laneHeight = canvasHeight / 4;
                const y = 50 + (car.lane * laneHeight);
                
                // Vẽ xe bằng emoji
                ctx.font = '30px Arial';
                ctx.fillText(car.emoji, x, y);
                
                // Hiển thị thời gian chờ nếu xe đang dừng
                if (car.waiting_time > 30) {
ctx.fillStyle = 'red';
                    ctx.font = '12px Arial';
                    ctx.fillText(`${car.waiting_time}s`, x, y - 10);
                }
            });
        }
        
        // Cập nhật giao diện
        function updateDisplay(data) {
            document.getElementById('cycle').textContent = data.current_cycle;
            document.getElementById('maxCycle').textContent = data.max_cycles;
            document.getElementById('vehiclesPassed').textContent = data.total_vehicles_passed || 0;
            
            // Cập nhật trạng thái đèn
            const stateDisplay = document.getElementById('stateDisplay');
            stateDisplay.textContent = data.light_state.toUpperCase();
            stateDisplay.className = 'light-state state-' + data.light_state;
            
            // Cập nhật timer
            document.getElementById('timer').textContent = data.remaining_time.toFixed(1) + 's';
            
            // Cập nhật ưu tiên
            const priorityDisplay = document.getElementById('priorityDisplay');
            if (data.priority_active) {
                priorityDisplay.style.display = 'block';
                document.getElementById('priorityType').textContent = 
                    data.priority_type.toUpperCase() + ' ƯU TIÊN';
            } else {
                priorityDisplay.style.display = 'none';
            }
            
            // Cập nhật log
            const logElement = document.getElementById('log');
            logElement.innerHTML = data.log.map(entry => 
                `<div class="log-entry"><span class="log-time">${entry.substring(1, 9)}</span> ${entry.substring(12)}</div>`
            ).join('');
            logElement.scrollTop = logElement.scrollHeight;
        }
        
        // Vẽ toàn bộ cảnh
        function drawScene(data) {
            // Xóa canvas
            ctx.clearRect(0, 0, canvasWidth, canvasHeight);
            
            // Vẽ các thành phần
            drawRoad();
            drawTrafficLight(data.light_state);
            drawCars(data.cars);
        }
        
        // Lấy dữ liệu từ server
        async function fetchData() {
            try {
                const response = await fetch('traffic_data.json?t=' + new Date().getTime());
                simulationData = await response.json();
                updateDisplay(simulationData);
                drawScene(simulationData);
            } catch (error) {
                console.error('Lỗi khi tải dữ liệu:', error);
            }
        }
        
        // Xóa log
        function clearLog() {
            const logElement = document.getElementById('log');
            logElement.innerHTML = '';
        }
        
        // Bắt đầu cập nhật
        setInterval(fetchData, 500);
        fetchData();
    </script>
</body>
</html>"""

# ==============================
# 🕹️ WEB SERVER
# ==============================
class TrafficHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Tắt log mặc định của HTTP server
        pass

def start_web_server():
    # Tạo file HTML
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    
    # Khởi động server
    PORT = 8000
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    with socketserver.TCPServer(("", PORT), TrafficHTTPRequestHandler) as httpd:
        print(f"🌐 Server đang chạy tại: http://localhost:{PORT}")
        print("🔄 Đang khởi động mô phỏng giao thông...")
        webbrowser.open(f"http://localhost:{PORT}/{HTML_FILE}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n⏹️ Dừng server...")

# ==============================
# 🚀 CHƯƠNG TRÌNH CHÍNH
# ==============================
def main():
    print("=" * 60)
    print("🚦 HỆ THỐNG ĐÈN GIAO THÔNG THÔNG MINH AI")
    print("   Sử dụng Edge Computing & Artificial Intelligence")
    print("=" * 60)
    
    # Xóa log cũ
    if os.path.exists(CONFIG["LOG_FILE"]):
        os.remove(CONFIG["LOG_FILE"])
    
    # Khởi tạo hệ thống
    traffic_manager = TrafficManager()
    
    def run_simulation():
        logger.log("🎬 Bắt đầu mô phỏng hệ thống đèn giao thông thông minh", "SYSTEM")
        
        try:
            for cycle in range(1, CONFIG["MAX_CYCLES"] + 1):
                traffic_manager.run_cycle(cycle)
                
                # Nghỉ giữa các chu kỳ
                if cycle < CONFIG["MAX_CYCLES"]:
                    time.sleep(2)
            
            logger.log("✅ Mô phỏng hoàn tất! Tổng số xe đã qua: " + 
                      str(traffic_manager.light.total_vehicles_passed), "SYSTEM")
                      
        except Exception as e:
            logger.log(f"❌ Lỗi trong mô phỏng: {str(e)}", "ERROR")
    
    # Chạy mô phỏng trong thread riêng
    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()
    
    # Khởi động web server
    start_web_server()

if __name__ == "__main__":
    main()
