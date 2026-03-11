#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Панель управления манипулятором - Модуль А

import sys
from datetime import datetime
from collections import deque
from math import pi
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMainWindow, QApplication, QFileDialog

USE_FAKE_API = True

if USE_FAKE_API:
    from fake_motion import RobotControl
else:
    try:
        from motion.core import RobotControl
    except ImportError:
        print("motion-core-api не установлен")
        sys.exit(1)


class LogManager:
    # Логгер - пишет в файл и хранит последние 3 записи
    
    def __init__(self, log_file="robot_logs.log", max_lines=3):
        self.log_file = log_file
        self.max_lines = max_lines
        self.logs = deque(maxlen=max_lines)
        self._init_file()
    
    def _init_file(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("СЕССИЯ: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n")
            f.write("=" * 60 + "\n")
    
    def log(self, msg, level="INFO"):
        time = datetime.now().strftime('%H:%M:%S')
        full_msg = "[" + time + "] [" + level + "] " + msg
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
    # Поток для опроса статуса робота
    
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
                    
                    data = {
                        'temp': temp,
                        'joints': joints
                    }
                    self.signal.emit(data)
            except:
                pass
            self.msleep(200)
    
    def stop(self):
        self.stop_flag = True
        self.wait()


class RobotCtrl:
    # Контроллер для управления роботом
    
    def __init__(self, ip="192.168.2.100", logger=None):
        self.ip = ip
        self.log = logger.log if logger else lambda x,y=None: None
        self.robot = None
        self.thread = None
        self.connected = False
        self.engaged = False
        self.manual = False
        self.mode = "CART"
        self.state = "GRAY"
        self.slider_values = [0.0] * 6
    
    def connect(self):
        try:
            self.log("Подключение к " + self.ip, "INFO")
            self.robot = RobotControl(self.ip)
            if self.robot.connect():
                self.connected = True
                self.state = "BLUE"
                self.log("Подключено", "SUCCESS")
                self.thread = RobotThread(self.robot)
                self.thread.signal.connect(self._on_data)
                self.thread.start()
                return True
            return False
        except Exception as e:
            self.log("Ошибка: " + str(e), "ERROR")
            return False
    
    def disconnect(self):
        if self.engaged:
            self.disengage()
        if self.thread:
            self.thread.stop()
        if self.robot:
            self.robot.disconnect()
            self.connected = False
            self.state = "GRAY"
            self.log("Отключено", "INFO")
    
    def engage(self):
        if not self.connected:
            return False
        if self.robot.engage():
            self.engaged = True
            self.log("Двигатели ВКЛ", "SUCCESS")
            return True
        return False
    
    def disengage(self):
        if not self.connected:
            return False
        if self.robot.disengage():
            self.engaged = False
            self.manual = False
            self.state = "BLUE"
            self.log("Двигатели ВЫКЛ", "INFO")
            return True
        return False
    
    def emergency(self):
        self.log("АВАРИЯ", "CRITICAL")
        try:
            self.robot.disengage()
            self.engaged = False
            self.manual = False
            self.state = "RED"
        except:
            pass
    
    def start_manual(self):
        if not self.connected or not self.engaged:
            return False
        self.manual = True
        self.state = "GREEN"
        self.log("Ручной режим", "INFO")
        return True
    
    def pause(self):
        self.state = "YELLOW"
        self.log("Пауза", "INFO")
    
    def toggle_mode(self):
        if not self.connected:
            return False
        if self.mode == "CART":
            if self.robot.manualJointMode():
                self.mode = "JOINT"
                self.log("Режим: JOINT", "INFO")
                return True
        else:
            if self.robot.manualCartMode():
                self.mode = "CART"
                self.log("Режим: CART", "INFO")
                return True
        return False
    
    def move(self, vel):
        if not self.engaged or not self.manual:
            return False
        vel = [max(-0.05, min(0.05, v)) for v in vel]
        try:
            if self.mode == "JOINT":
                return self.robot.setJointVelocity(vel)
            else:
                return self.robot.setCartesianVelocity(vel)
        except:
            return False
    
    def stop_move(self):
        if self.engaged:
            self.move([0.0]*6)
    
    def to_start(self):
        if self.connected:
            self.log("На старт", "INFO")
            return self.robot.moveToStart()
        return False
    
    def move_l(self):
        if self.connected:
            return self.toggle_mode()
        return False
    
    def gripper_open(self):
        if self.robot.toolOFF():
            self.log("Клешня ОТКРЫТА", "INFO")
            return True
        return False
    
    def gripper_close(self):
        if self.robot.toolON():
            self.log("Клешня ЗАКРЫТА", "INFO")
            return True
        return False
    
    def update_slider_value(self, idx, val):
        self.slider_values[idx] = val
    
    def _on_data(self, data):
        pass


class MainWindow(QMainWindow):
    # Основное окно приложения
    
    def __init__(self):
        super().__init__()
        self.logger = LogManager()
        self.robot = RobotCtrl(logger=self.logger)
        self.robot._on_data = self.update_table
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.stop_move)
        
        from design import Ui_MainWindow
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Управление манипулятором")
        
        self.sliders = [self.ui.ox, self.ui.oy, self.ui.oa, 
                       self.ui.rx, self.ui.ry, self.ui.rz]
        self.labels = [self.ui.label, self.ui.label_2, self.ui.label_3,
                      self.ui.label_4, self.ui.label_5, self.ui.label_6]
        self.header_cart = ["X", "Y", "Z", "RX", "RY", "RZ"]
        self.header_joint = ["J1", "J2", "J3", "J4", "J5", "J6"]
        
        for s in self.sliders:
            s.setRange(-100, 100)
            s.setValue(0)
            s.setEnabled(False)
        
        # Настройка таблицы - 7 строк
        self.ui.tableWidget.setRowCount(7)
        self.ui.tableWidget.setColumnCount(6)
        
        self._create_traffic_light()
        self.update_labels()
        self.connect_signals()
        self.logger.log("Запуск", "INFO")
        self.update_logs()
        self.update_traffic_light()
    
    def _create_traffic_light(self):
        # Создание индикатора состояния
        self.traffic_light = QtWidgets.QLabel(self.ui.centralwidget)
        self.traffic_light.setGeometry(QtCore.QRect(440, 360, 80, 80))
        self.traffic_light.setStyleSheet("""
            QLabel { background-color: #4a4a4a; border-radius: 40px; border: 4px solid #2a2a2a; }
        """)
    
    def update_traffic_light(self):
        # Обновление цвета светофора
        state = self.robot.state
        colors = {
            "RED": ("#ff0000", "0 0 20px #ff0000"),
            "YELLOW": ("#ffaa00", "0 0 20px #ffaa00"),
            "GREEN": ("#00ff00", "0 0 20px #00ff00"),
            "BLUE": ("#4444ff", "0 0 20px #4444ff"),
            "GRAY": ("#4a4a4a", "none")
        }
        color, glow = colors.get(state, ("#4a4a4a", "none"))
        self.traffic_light.setStyleSheet("""
            QLabel { background-color: %s; border-radius: 40px; border: 4px solid #2a2a2a; box-shadow: %s; }
        """ % (color, glow))
        
        msg = {"GRAY": "Выключена", "BLUE": "Ожидание", "GREEN": "Ручной", 
               "YELLOW": "Пауза", "RED": "АВАРИЯ"}
        self.ui.statusbar.showMessage(msg.get(state, ""))
    
    def connect_signals(self):
        # Подключение кнопок
        self.ui.pushButton_3.clicked.connect(self.toggle_system)
        self.ui.rezim.clicked.connect(self.start_manual)
        self.ui.off.clicked.connect(self.motors_off)
        self.ui.stop.clicked.connect(self.emergency)
        self.ui.pause.clicked.connect(self.pause)
        self.ui.pushButton.clicked.connect(self.to_start)
        self.ui.pushButton_4.clicked.connect(self.move_l)
        self.ui.open.clicked.connect(self.gripper_open)
        self.ui.close.clicked.connect(self.gripper_close)
        self.ui.savesistem.clicked.connect(self.save_state)
        self.ui.save.clicked.connect(self.save_logs)
        for i, s in enumerate(self.sliders):
            s.valueChanged.connect(lambda v, idx=i: self.slider_move(idx, v))
    
    def update_labels(self):
        # Обновление подписей
        if self.robot.mode == "JOINT":
            names = ["J1", "J2", "J3", "J4", "J5", "J6"]
            headers = self.header_joint
        else:
            names = ["X", "Y", "Z", "RX", "RY", "RZ"]
            headers = self.header_cart
        for lbl, name in zip(self.labels, names):
            lbl.setText(name)
        self.ui.tableWidget.setHorizontalHeaderLabels(headers)
    
    def toggle_system(self):
        # Включение/выключение системы
        if not self.robot.connected:
            if self.robot.connect():
                self.ui.pushButton_3.setText("ВЫКЛЮЧИТЬ СИСТЕМУ")
                self.ui.pushButton_3.setStyleSheet("color: red; font-weight: bold; font-size: 17pt")
                self.enable_controls(True)
                self.update_traffic_light()
                self.logger.log("Система включена", "INFO")
        else:
            self.robot.disconnect()
            self.ui.pushButton_3.setText("ВКЛЮЧЕНИЕ СИСТЕМЫ")
            self.ui.pushButton_3.setStyleSheet("color: green; font-weight: bold; font-size: 17pt")
            self.enable_controls(False)
            for s in self.sliders:
                s.setEnabled(False)
            self.logger.log("Система выключена", "INFO")
    
    def start_manual(self):
        # Запуск ручного режима
        self.logger.log("Ручной режим запущен", "INFO")
        if self.robot.engage():
            if self.robot.start_manual():
                self.update_traffic_light()
                for s in self.sliders:
                    s.setEnabled(True)
                self.update_logs()
    
    def motors_off(self):
        # Выключение двигателей
        self.logger.log("Двигатели ВЫКЛ", "INFO")
        self.robot.disengage()
        self.stop_move()
        self.update_traffic_light()
        for s in self.sliders:
            s.setEnabled(False)
        self.update_logs()
    
    def emergency(self):
        # Аварийная остановка
        self.logger.log("АВАРИЙНАЯ ОСТАНОВКА", "CRITICAL")
        self.robot.emergency()
        self.stop_move()
        self.enable_controls(False)
        self.update_traffic_light()
        for s in self.sliders:
            s.setEnabled(False)
        self.update_logs()
    
    def pause(self):
        # Пауза
        self.logger.log("Пауза", "INFO")
        self.robot.pause()
        self.update_traffic_light()
        self.stop_move()
        self.update_logs()
    
    def to_start(self):
        # Возврат на старт
        self.logger.log("Возврат на старт", "INFO")
        self.robot.to_start()
        self.update_logs()
    
    def move_l(self):
        # Переключение режима
        if self.robot.move_l():
            self.update_labels()
            self.update_logs()
    
    def gripper_open(self):
        # Открытие клешни
        self.logger.log("Клешня ОТКРЫТА", "INFO")
        self.robot.gripper_open()
        self.update_logs()
    
    def gripper_close(self):
        # Закрытие клешни
        self.logger.log("Клешня ЗАКРЫТА", "INFO")
        self.robot.gripper_close()
        self.update_logs()
    
    def slider_move(self, idx, val):
        # Обработка слайдера
        if not self.robot.engaged or not self.robot.manual:
            return
        
        vel = val / 2000.0
        vels = [0.0]*6
        vels[idx] = vel
        
        # Сохраняем и обновляем таблицу
        self.robot.update_slider_value(idx, vel)
        self.update_slider_table(idx, vel)
        
        # Отправляем команду роботу
        self.robot.move(vels)
        self.timer.start()
    
    def stop_move(self):
        # Остановка движения
        self.timer.stop()
        self.robot.stop_move()
    
    def update_table(self, data):
        # Обновление таблицы - ТОЛЬКО температура из API
        if not data:
            return
        
        # Строка 0: Температура (обновляется каждые 200мс)
        if data.get('temp'):
            temp = data['temp']
            for col in range(6):
                item = QtWidgets.QTableWidgetItem(str(round(temp, 1)) + " C")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.ui.tableWidget.setItem(0, col, item)
        
        # Строка 2: НЕ ТРОГАЕМ! (остается от слайдеров)
    
    def update_slider_table(self, idx, val):
        # Обновление строки 2 - значения остаются пока не тронешь слайдер снова
        item = QtWidgets.QTableWidgetItem(str(round(val, 4)))
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        self.ui.tableWidget.setItem(2, idx, item)
    
    def update_logs(self):
        # Обновление списка логов
        self.ui.listWidget.clear()
        for log in self.logger.get_logs():
            item = QtWidgets.QListWidgetItem(log)
            if "ERROR" in log or "CRITICAL" in log:
                item.setForeground(QtGui.QColor("#ff4444"))
            elif "WARN" in log:
                item.setForeground(QtGui.QColor("#ffaa00"))
            else:
                item.setForeground(QtGui.QColor("#00aa00"))
            self.ui.listWidget.addItem(item)
        self.ui.listWidget.scrollToBottom()
    
    def enable_controls(self, en):
        # Включение кнопок
        btns = [self.ui.rezim, self.ui.off, self.ui.stop, self.ui.pause,
               self.ui.pushButton, self.ui.pushButton_4, self.ui.savesistem,
               self.ui.open, self.ui.close, self.ui.save]
        for b in btns:
            b.setEnabled(en)
    
    def save_logs(self):
        # Сохранение логов
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить логи",
            "log_" + datetime.now().strftime('%Y%m%d_%H%M%S') + ".txt",
            "Text Files (*.txt)")
        if path:
            if self.logger.save_log(path):
                self.logger.log("Логи сохранены", "INFO")
                self.update_logs()
    
    def save_state(self):
        # Сохранение состояния
        self.logger.log("Состояние сохранено", "INFO")
        self.update_logs()
    
    def closeEvent(self, ev):
        # Закрытие приложения
        self.logger.log("Завершение", "INFO")
        self.timer.stop()
        self.robot.disconnect()
        ev.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QtGui.QFont("Segoe UI", 10))
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())