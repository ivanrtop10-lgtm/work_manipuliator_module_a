import os
import sys
from pathlib import Path

venv_base = Path(__file__).parent / ".venv"
plugin_path = venv_base / "lib" / "python3.12" / "site-packages" / "PyQt5" / "Qt5" / "plugins" / "platforms"
if plugin_path.exists():
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = str(plugin_path)
else:
    try:
        import PyQt5
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(
            os.path.dirname(PyQt5.__file__), "Qt5", "plugins", "platforms"
        )
    except ImportError:
        pass

from datetime import datetime
from collections import deque
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMainWindow, QApplication, QFileDialog

from fake_motion import RobotControl

class LogManager:
    def __init__(self, log_file="robot_logs.log"):
        self.log_file = log_file
        self.logs = deque(maxlen=50)
        self._init_file()

    def _init_file(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("Начало сессии: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n")
            f.write("=" * 60 + "\n")

    def log(self, msg):
        time = datetime.now().strftime('%H:%M:%S')
        full_msg = time + " - " + msg
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(full_msg + "\n")
        self.logs.append(full_msg)
        return list(self.logs)

    def get_logs(self):
        return list(self.logs)

    def save_log(self, path):
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                with open(path, 'w', encoding='utf-8') as out:
                    out.write(f.read())
            return True
        except:
            return False

class RobotThread(QtCore.QThread):
    signal = QtCore.pyqtSignal(dict)

    def __init__(self, robot):
        super().__init__()
        self.robot = robot
        self.stop_flag = False

    def run(self):
        while not self.stop_flag:
            try:
                if self.robot and self.robot.connected:
                    temp = self.robot.getActualTemperature()
                    joints = self.robot.getMotorPositionRadians()
                    data = {'temp': temp, 'joints': joints}
                    self.signal.emit(data)
            except:
                pass
            self.msleep(200)

    def stop(self):
        self.stop_flag = True
        self.wait()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = LogManager()
        self.robot = RobotControl("192.168.2.100")
        self.thread = None
        self.connected = False
        self.engaged = False
        self.manual = False
        self.mode = "CART"
        self.state = "GRAY"
        self.object_counters = [0, 0, 0]
        self.joystick_values = [0.0] * 6
        
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.stop_move)
        
        from design2 import Ui_MainWindow
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Управление манипулятором")
        
        self.sliders = [self.ui.ox, self.ui.oy, self.ui.oa, 
                       self.ui.rx, self.ui.ry, self.ui.rz]
        self.labels = [self.ui.label, self.ui.label_2, self.ui.label_3,
                      self.ui.label_4, self.ui.label_5, self.ui.label_6]
        
        for s in self.sliders:
            s.setRange(-100, 100)
            s.setValue(0)
            s.setEnabled(False)
        
        # Таблица - 4 строки (как в design2.py)
        self.ui.tableWidget.setRowCount(4)
        self.ui.tableWidget.setColumnCount(6)
        
        # Поле для имени файла (вместо listWidget_2)
        self.filename_input = QtWidgets.QLineEdit(self.ui.centralwidget)
        self.filename_input.setGeometry(QtCore.QRect(1040, 560, 211, 31))
        self.filename_input.setPlaceholderText("Введите имя файла")
        self.filename_input.setText("default_log.txt")
        
        # Скрываем listWidget_2
        if hasattr(self.ui, 'listWidget_2'):
            self.ui.listWidget_2.hide()
        
        # Инициализация таблицы brak
        self.init_brak_table()
        
        # Инициализация таблицы tableWidget_2
        self.init_status_table()
        
        self._create_traffic_light()
        self.connect_signals()
        self.logger.log("Запуск")
        self.update_logs()
        self.update_traffic_light()

    def init_brak_table(self):
        self.ui.brak.setColumnCount(2)
        for i in range(3):
            item = QtWidgets.QTableWidgetItem("0")
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.ui.brak.setItem(i, 0, item)
            item_time = QtWidgets.QTableWidgetItem("-")
            item_time.setTextAlignment(QtCore.Qt.AlignCenter)
            self.ui.brak.setItem(i, 1, item_time)

    def init_status_table(self):
        self.ui.tableWidget_2.setColumnCount(6)
        self.ui.tableWidget_2.setRowCount(2)
        for row in range(2):
            for col in range(6):
                item = QtWidgets.QTableWidgetItem("-")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.ui.tableWidget_2.setItem(row, col, item)

    def _create_traffic_light(self):
        self.traffic_light = QtWidgets.QLabel(self.ui.centralwidget)
        self.traffic_light.setGeometry(QtCore.QRect(440, 360, 80, 80))
        self.traffic_light.setStyleSheet("""
            QLabel { background-color: #4a4a4a; border-radius: 40px; border: 4px solid #2a2a2a; }
        """)

    def update_traffic_light(self):
        colors = {
            "RED": ("#ff0000", "0 0 20px #ff0000"),
            "YELLOW": ("#ffaa00", "0 0 20px #ffaa00"),
            "GREEN": ("#00ff00", "0 0 20px #00ff00"),
            "BLUE": ("#4444ff", "0 0 20px #4444ff"),
            "GRAY": ("#4a4a4a", "none")
        }
        color, glow = colors.get(self.state, ("#4a4a4a", "none"))
        self.traffic_light.setStyleSheet("""
            QLabel { background-color: %s; border-radius: 40px; border: 4px solid #2a2a2a; box-shadow: %s; }
        """ % (color, glow))
        
        msg = {"GRAY": "Выключена", "BLUE": "Ожидание", "GREEN": "Ручной", 
                "YELLOW": "Пауза", "RED": "АВАРИЯ"}
        self.ui.statusbar.showMessage(msg.get(self.state, ""))

    def connect_signals(self):
        self.ui.pushButton_3.clicked.connect(self.toggle_system)
        self.ui.rezim.clicked.connect(self.start_manual)
        self.ui.stop.clicked.connect(self.emergency)
        self.ui.pause.clicked.connect(self.pause)
        self.ui.pushButton.clicked.connect(self.to_start)
        self.ui.pushButton_4.clicked.connect(self.move_l)  # Кнопка move l
        self.ui.close.clicked.connect(self.toggle_gripper)
        self.ui.savesistem.clicked.connect(self.save_state)
        self.ui.save.clicked.connect(self.save_logs)
        
        self.ui.pushButton_2.clicked.connect(lambda: self.add_object_value(0))
        self.ui.pushButton_5.clicked.connect(lambda: self.add_object_value(1))
        self.ui.pushButton_6.clicked.connect(lambda: self.add_object_value(2))
        
        for i, s in enumerate(self.sliders):
            s.valueChanged.connect(lambda v, idx=i: self.slider_move(idx, v))

    def toggle_system(self):
        if not self.connected:
            try:
                if self.robot.connect():
                    self.connected = True
                    self.state = "BLUE"
                    self.ui.pushButton_3.setText("ВЫКЛЮЧИТЬ СИСТЕМУ")
                    self.ui.pushButton_3.setStyleSheet("color: red; font-weight: bold; font-size: 17pt")
                    self.enable_controls(True)
                    self.update_traffic_light()
                    self.logger.log("Система включена")
                    
                    self.thread = RobotThread(self.robot)
                    self.thread.signal.connect(self.update_table)
                    self.thread.start()
            except Exception as e:
                self.logger.log("Ошибка: " + str(e))
        else:
            if self.engaged:
                self.robot.disengage()
                self.engaged = False
            if self.thread:
                self.thread.stop()
            try:
                self.robot.disconnect()
            except:
                pass
            self.connected = False
            self.state = "GRAY"
            self.ui.pushButton_3.setText("ВКЛЮЧЕНИЕ СИСТЕМЫ")
            self.ui.pushButton_3.setStyleSheet("color: green; font-weight: bold; font-size: 17pt")
            self.enable_controls(False)
            for s in self.sliders:
                s.setEnabled(False)
            self.logger.log("Система выключена")

    def start_manual(self):
        if not self.connected:
            return
        if self.robot.engage():
            self.engaged = True
            self.logger.log("Двигатели ВКЛ")
            if self.mode == "CART":
                self.robot.manualCartMode()
            else:
                self.robot.manualJointMode()
            self.manual = True
            self.state = "GREEN"
            self.update_traffic_light()
            for s in self.sliders:
                s.setEnabled(True)
            self.update_logs()

    def emergency(self):
        self.logger.log("АВАРИЙНАЯ ОСТАНОВКА")
        self.robot.disengage()
        self.engaged = False
        self.manual = False
        self.state = "RED"
        self.stop_move()
        self.enable_controls(False)
        self.update_traffic_light()
        for s in self.sliders:
            s.setEnabled(False)
        self.update_logs()

    def pause(self):
        self.logger.log("Пауза")
        self.state = "YELLOW"
        self.stop_move()
        self.update_traffic_light()
        self.update_logs()

    def to_start(self):
        if self.connected:
            self.logger.log("Возврат на старт")
            self.robot.moveToStart()
            self.update_logs()

    def move_l(self):
        # Кнопка move l - МЕНЯЕТ ТОЛЬКО НАЗВАНИЯ ДЖОЙСТИКОВ, таблицу не трогает
        if self.connected:
            if self.mode == "CART":
                self.robot.manualJointMode()
                self.mode = "JOINT"
                # Меняем подписи на J1, J2, J3, J4, J5, J6
                names = ["J1", "J2", "J3", "J4", "J5", "J6"]
            else:
                self.robot.manualCartMode()
                self.mode = "CART"
                # Меняем подписи на X, Y, Z, RX, RY, RZ
                names = ["X", "Y", "Z", "RX", "RY", "RZ"]
            
            # Обновляем только подписи над слайдерами
            for lbl, name in zip(self.labels, names):
                lbl.setText(name)
            
            self.logger.log("Режим: " + self.mode)
            self.update_logs()

    def toggle_gripper(self):
        current_text = self.ui.close.text()
        if current_text == "закрытие гриппера":
            if self.robot.toolON():
                self.ui.close.setText("открытие гриппера")
                self.ui.close.setStyleSheet("color: green")
                self.logger.log("Гриппер ЗАКРЫТ")
                self.update_gripper_table("ЗАКРЫТ")
        else:
            if self.robot.toolOFF():
                self.ui.close.setText("закрытие гриппера")
                self.ui.close.setStyleSheet("color: red")
                self.logger.log("Гриппер ОТКРЫТ")
                self.update_gripper_table("ОТКРЫТ")
        self.update_logs()

    def update_gripper_table(self, state):
        for col in range(6):
            item = QtWidgets.QTableWidgetItem(state)
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.ui.tableWidget_2.setItem(1, col, item)

    def add_object_value(self, obj_index):
        self.object_counters[obj_index] += 1
        current_time = datetime.now().strftime('%H:%M:%S')
        
        item_count = QtWidgets.QTableWidgetItem(str(self.object_counters[obj_index]))
        item_count.setTextAlignment(QtCore.Qt.AlignCenter)
        self.ui.brak.setItem(obj_index, 0, item_count)
        
        item_time = QtWidgets.QTableWidgetItem(current_time)
        item_time.setTextAlignment(QtCore.Qt.AlignCenter)
        self.ui.brak.setItem(obj_index, 1, item_time)
        
        obj_name = "1" if obj_index == 0 else "2" if obj_index == 1 else "брак"
        self.logger.log("Объект " + obj_name + ": +1 (всего: " + str(self.object_counters[obj_index]) + ")")
        self.update_logs()

    def slider_move(self, idx, val):
        if not self.engaged or not self.manual:
            return
        vel = val / 2000.0
        vels = [0.0]*6
        vels[idx] = vel
        
        # СОХРАНЯЕМ значение джойстика
        self.joystick_values[idx] = val
        
        # Записываем в таблицу (строка 2 - радианы/джойстики)
        self.update_joystick_table(idx, vel)
        
        if self.mode == "JOINT":
            self.robot.setJointVelocity(vels)
        else:
            self.robot.setCartesianVelocity(vels)
        self.timer.start()

    def stop_move(self):
        # ОСТАНАВЛИВАЕМ движение, но НЕ СБРАСЫВАЕМ значения джойстиков в таблице
        self.timer.stop()
        if self.engaged:
            if self.mode == "JOINT":
                self.robot.setJointVelocity([0.0]*6)
            else:
                self.robot.setCartesianVelocity([0.0]*6)
        # Значения джойстиков остаются в таблице!

    def update_table(self, data):
        if not data:
            return
        
        # Строка 0: Температура (из API)
        if data.get('temp') is not None:
            temp = data['temp']
            for col in range(6):
                item = QtWidgets.QTableWidgetItem(str(round(temp, 1)) + " C")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.ui.tableWidget.setItem(0, col, item)
        
        # Строка 1: Тики (из API)
        if data.get('joints'):
            joints = data['joints']
            for col in range(6):
                ticks = int(joints[col] * 1000)
                item = QtWidgets.QTableWidgetItem(str(ticks))
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.ui.tableWidget.setItem(1, col, item)
                
                # Строка 3: Градусы (из API)
                item_deg = QtWidgets.QTableWidgetItem(str(round(joints[col] * 180 / 3.14159, 2)))
                item_deg.setTextAlignment(QtCore.Qt.AlignCenter)
                self.ui.tableWidget.setItem(3, col, item_deg)
                
                # Актуальная поза в tableWidget_2
                item_pose = QtWidgets.QTableWidgetItem(str(round(joints[col], 3)))
                item_pose.setTextAlignment(QtCore.Qt.AlignCenter)
                self.ui.tableWidget_2.setItem(0, col, item_pose)
        # Строка 2 (радианы/джойстики) НЕ ТРОГАЕМ - остаётся последнее значение!

    def update_joystick_table(self, idx, val):
        # Обновление строки 2 - значения джойстиков
        item = QtWidgets.QTableWidgetItem(str(round(val, 4)))
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        self.ui.tableWidget.setItem(2, idx, item)

    def update_logs(self):
        self.ui.listWidget.clear()
        for log in self.logger.get_logs():
            item = QtWidgets.QListWidgetItem(log)
            item.setForeground(QtGui.QColor("#00aa00"))
            self.ui.listWidget.addItem(item)
        self.ui.listWidget.scrollToBottom()

    def enable_controls(self, en):
        btns = [self.ui.rezim, self.ui.stop, self.ui.pause,
               self.ui.pushButton, self.ui.pushButton_4, self.ui.savesistem,
               self.ui.close, self.ui.save]
        for b in btns:
            b.setEnabled(en)

    def save_logs(self):
        filename = self.filename_input.text().strip()
        if not filename:
            filename = "log_" + datetime.now().strftime('%Y%m%d_%H%M%S') + ".txt"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить логи", filename, "Text Files (*.txt)")
        if path:
            if self.logger.save_log(path):
                self.logger.log("Логи сохранены в: " + path)
                self.update_logs()

    def save_state(self):
        self.logger.log("Состояние сохранено")
        self.update_logs()

    def closeEvent(self, ev):
        self.logger.log("Завершение")
        self.timer.stop()
        if self.thread:
            self.thread.stop()
        if self.robot and self.connected:
            if self.engaged:
                self.robot.disengage()
            try:
                self.robot.disconnect()
            except:
                pass
        ev.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QtGui.QFont("Segoe UI", 10))
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())