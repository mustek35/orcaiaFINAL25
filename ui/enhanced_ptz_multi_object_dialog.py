# ui/enhanced_ptz_multi_object_dialog.py - VERSIÓN CORREGIDA
"""
Diálogo PTZ mejorado con seguimiento multi-objeto y zoom inteligente - CORREGIDO
Interfaz completa para control avanzado de cámaras PTZ con capacidades:
- Seguimiento de múltiples objetos con alternancia
- Zoom automático inteligente  
- Configuración de prioridades
- Monitoreo en tiempo real
- Estadísticas y análisis

CORRECCIÓN APLICADA: Solucionado error 'NoneType' object has no attribute 'get'
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QComboBox, QLabel,
    QMessageBox, QGroupBox, QCheckBox, QSpinBox, QTextEdit, QSlider, QProgressBar,
    QDoubleSpinBox, QTabWidget, QWidget, QFormLayout, QSplitter, QListWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QScrollArea,
    QLineEdit, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QBrush
import threading
import time
import json
import os
import sys
from typing import Optional, Dict, List, Any
from datetime import datetime

# Importar sistema multi-objeto
try:
    from core.multi_object_ptz_system import (
        MultiObjectPTZTracker, MultiObjectConfig, TrackingMode, ObjectPriority,
        create_multi_object_tracker, get_preset_config, PRESET_CONFIGS,
        analyze_tracking_performance
    )
    MULTI_OBJECT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Sistema multi-objeto no disponible: {e}")
    MULTI_OBJECT_AVAILABLE = False

# Importar sistema de integración
try:
    from core.ptz_tracking_integration_enhanced import (
        PTZTrackingSystemEnhanced, start_ptz_session, stop_ptz_session,
        update_ptz_detections, process_ptz_yolo_results, get_ptz_status
    )
    INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Sistema de integración no disponible: {e}")
    INTEGRATION_AVAILABLE = False

# Importar sistema básico como fallback
try:
    from core.ptz_control import PTZCameraONVIF
    BASIC_PTZ_AVAILABLE = True
except ImportError:
    BASIC_PTZ_AVAILABLE = False

# === CLASE STATUSUPDATETHREAD CORREGIDA ===
class StatusUpdateThread(QThread):
    """Hilo CORREGIDO para actualizar estado del sistema PTZ"""
    status_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, tracker=None):
        super().__init__()
        self.tracker = tracker
        self.running = True
        self.error_count = 0
        self.max_errors = 10  # Máximo errores antes de detener
        
    def run(self):
        """Ejecutar actualizaciones de estado con manejo de errores mejorado"""
        while self.running:
            try:
                # Verificar que el tracker existe y es válido
                if not self.tracker:
                    time.sleep(1.0)
                    continue
                
                # Intentar obtener estado del tracker de forma segura
                status = self._get_safe_status()
                
                if status and isinstance(status, dict):
                    # Resetear contador de errores si obtenemos estado válido
                    self.error_count = 0
                    self.status_updated.emit(status)
                else:
                    # Incrementar contador de errores
                    self.error_count += 1
                    if self.error_count >= self.max_errors:
                        break
                
                # Esperar antes de la siguiente actualización
                time.sleep(0.5)  # 500ms entre actualizaciones
                
            except Exception as e:
                self.error_count += 1
                error_msg = f"Error en StatusThread: {e}"
                self.error_occurred.emit(error_msg)
                
                # Si hay demasiados errores, detener el hilo
                if self.error_count >= self.max_errors:
                    break
                
                # Esperar más tiempo si hay errores
                time.sleep(1.0)
    
    def _get_safe_status(self):
        """Obtener estado del tracker de forma segura"""
        try:
            # Verificar que el tracker tiene método get_status
            if not hasattr(self.tracker, 'get_status'):
                return self._create_default_status("Tracker sin método get_status")
            
            # Intentar obtener estado
            status = self.tracker.get_status()
            
            # Verificar que el estado es válido
            if status is None:
                return self._create_default_status("Estado None retornado")
            
            # Verificar que es un diccionario
            if not isinstance(status, dict):
                return self._create_default_status(f"Estado inválido: {type(status)}")
            
            # Asegurar campos mínimos requeridos
            safe_status = self._ensure_required_fields(status)
            return safe_status
            
        except Exception as e:
            return self._create_default_status(f"Error: {e}")
    
    def _ensure_required_fields(self, status):
        """Asegurar que el estado tiene todos los campos requeridos"""
        safe_status = {
            'connected': status.get('connected', False),
            'tracking_active': status.get('tracking_active', False),
            'successful_moves': status.get('successful_moves', 0),
            'failed_moves': status.get('failed_moves', 0),
            'total_detections': status.get('total_detections', 0),
            'success_rate': status.get('success_rate', 0.0),
            'ip': status.get('ip', 'unknown'),
            'active_objects': status.get('active_objects', 0),
            'current_target': status.get('current_target', None),
            'camera_ip': status.get('camera_ip', status.get('ip', 'unknown')),
            'session_time': status.get('session_time', 0),
            'switches_count': status.get('switches_count', 0),
            'last_update': time.time()
        }
        return safe_status
    
    def _create_default_status(self, reason="Estado no disponible"):
        """Crear estado por defecto cuando no se puede obtener del tracker"""
        return {
            'connected': False,
            'tracking_active': False,
            'successful_moves': 0,
            'failed_moves': 0,
            'total_detections': 0,
            'success_rate': 0.0,
            'ip': 'unknown',
            'active_objects': 0,
            'current_target': None,
            'camera_ip': 'unknown',
            'session_time': 0,
            'switches_count': 0,
            'status_error': reason,
            'last_update': time.time()
        }
    
    def stop(self):
        """Detener el hilo de forma segura"""
        self.running = False

class EnhancedMultiObjectPTZDialog(QDialog):
    """Diálogo principal para control PTZ multi-objeto"""
    
    # Señales para comunicación
    tracking_started = pyqtSignal()
    tracking_stopped = pyqtSignal()
    object_detected = pyqtSignal(int, dict)
    object_lost = pyqtSignal(int)
    target_switched = pyqtSignal(int, int)
    zoom_changed = pyqtSignal(float, float)
    tracking_stats_updated = pyqtSignal(dict)
    
    def __init__(self, parent=None, camera_list=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Control PTZ Multi-Objeto Avanzado")
        self.setMinimumSize(900, 700)
        
        # Verificar disponibilidad de sistemas
        if not MULTI_OBJECT_AVAILABLE and not INTEGRATION_AVAILABLE:
            self._show_error_dialog()
            return
        
        # Datos del sistema
        self.all_cameras = camera_list or []
        self.current_camera_data = None
        self.tracking_active = False
        self.current_camera_id = None
        
        # Sistema PTZ
        self.current_tracker = None
        self.status_thread = None
        
        # Configuración
        if MULTI_OBJECT_AVAILABLE:
            self.multi_config = MultiObjectConfig()
        else:
            self.multi_config = None
            
        self.config_file = "ptz_multi_object_ui_config.json"
        
        # Estadísticas
        self.detection_count = 0
        self.session_start_time = 0
        self.performance_history = []
        
        # Timer para actualización de UI
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self._update_ui_displays)
        self.ui_update_timer.start(1000)  # Cada segundo
        
        # Configurar interfaz
        self._setup_enhanced_ui()
        self._connect_all_signals()
        self._load_camera_configuration()
        self._load_ui_configuration()
        
        # Aplicar tema
        self._apply_dark_theme()
        
        self._log("🎯 Sistema PTZ Multi-Objeto inicializado")

    def closeEvent(self, event):
        """Manejar cierre del diálogo con limpieza completa de recursos"""
        print("INFO: Iniciando cierre de EnhancedMultiObjectPTZDialog...")
        
        try:
            # Detener seguimiento si está activo
            if hasattr(self, 'tracking_active') and self.tracking_active:
                self._log("🛑 Deteniendo seguimiento antes del cierre...")
                self._stop_tracking()
            
            # Detener hilo de estado
            if hasattr(self, 'status_thread') and self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)  # Esperar máximo 2 segundos
                
            # Detener timer de UI
            if hasattr(self, 'ui_update_timer') and self.ui_update_timer:
                self.ui_update_timer.stop()
            
            # Limpiar tracker
            if hasattr(self, 'current_tracker') and self.current_tracker:
                try:
                    if hasattr(self.current_tracker, 'cleanup'):
                        self.current_tracker.cleanup()
                    self.current_tracker = None
                    print("INFO: Tracker PTZ limpiado")
                except Exception as e:
                    print(f"WARN: Error limpiando tracker: {e}")
            
            # Guardar configuración antes del cierre
            self._save_ui_configuration()
            
            print("INFO: Cierre de EnhancedMultiObjectPTZDialog completado")
            event.accept()
            
        except Exception as e:
            print(f"ERROR: Error durante cierre: {e}")
            event.accept()  # Forzar cierre incluso con errores

    def _setup_enhanced_ui(self):
        """Configurar interfaz de usuario mejorada"""
        layout = QVBoxLayout(self)
        
        # === HEADER ===
        header_frame = QFrame()
        header_frame.setFixedHeight(60)
        header_layout = QHBoxLayout(header_frame)
        
        title_label = QLabel("🎯 Control PTZ Multi-Objeto Avanzado")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
                background: transparent;
            }
        """)
        
        self.system_status_label = QLabel("🔴 Sistema Inactivo")
        self.system_status_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 15px;
                background-color: #2d1b1b;
                color: #dc3545;
            }
        """)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.system_status_label)
        
        layout.addWidget(header_frame)
        
        # === TABS PRINCIPALES ===
        self.main_tabs = QTabWidget()
        layout.addWidget(self.main_tabs)
        
        # Tab Control
        self._create_control_tab()
        
        # Tab Configuración
        self._create_config_tab()
        
        # Tab Monitoreo
        self._create_monitoring_tab()
        
        # Tab Estadísticas
        self._create_stats_tab()
        
        # === STATUS BAR ===
        status_frame = QFrame()
        status_frame.setFixedHeight(40)
        status_layout = QHBoxLayout(status_frame)
        
        self.camera_status_label = QLabel("📷 Sin cámara")
        self.tracking_time_label = QLabel("⏱️ 00:00:00")
        self.detection_count_label = QLabel("🎯 0 detecciones")
        
        status_layout.addWidget(self.camera_status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.tracking_time_label)
        status_layout.addWidget(self.detection_count_label)
        
        layout.addWidget(status_frame)

    def _create_control_tab(self):
        """Crear tab de control principal"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # === SELECCIÓN DE CÁMARA ===
        camera_group = QGroupBox("📷 Selección de Cámara")
        camera_layout = QFormLayout(camera_group)
        
        self.camera_selector = QComboBox()
        self.camera_selector.addItem("Seleccionar cámara...")
        
        # Cargar cámaras PTZ disponibles
        ptz_cameras = [cam for cam in self.all_cameras if cam.get('tipo') == 'ptz']
        for camera in ptz_cameras:
            camera_name = f"{camera.get('nombre', camera.get('ip', 'Sin nombre'))} ({camera.get('ip', 'Sin IP')})"
            self.camera_selector.addItem(camera_name, camera)
        
        camera_layout.addRow("Cámara PTZ:", self.camera_selector)
        layout.addWidget(camera_group)
        
        # === CONTROL DE SEGUIMIENTO ===
        tracking_group = QGroupBox("🎯 Control de Seguimiento")
        tracking_layout = QVBoxLayout(tracking_group)
        
        # Botones principales
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("🚀 Iniciar Seguimiento")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        self.stop_btn = QPushButton("⏹️ Detener")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addStretch()
        
        tracking_layout.addLayout(button_layout)
        
        # Modo de seguimiento
        mode_layout = QFormLayout()
        
        self.tracking_mode_selector = QComboBox()
        self.tracking_mode_selector.addItems([
            "Objeto Individual",
            "Multi-Objeto Alternante",
            "Basado en Prioridad",
            "Cambio Automático"
        ])
        self.tracking_mode_selector.setCurrentText("Multi-Objeto Alternante")
        
        mode_layout.addRow("Modo:", self.tracking_mode_selector)
        
        tracking_layout.addLayout(mode_layout)
        layout.addWidget(tracking_group)
        
        # === ESTADO ACTUAL ===
        status_group = QGroupBox("📊 Estado Actual")
        status_layout = QGridLayout(status_group)
        
        # Labels de estado
        self.connection_status_label = QLabel("🔴 Desconectado")
        self.tracking_status_label = QLabel("⏸️ Inactivo")
        self.objects_count_label = QLabel("0")
        self.current_target_label = QLabel("➖ Sin objetivo")
        
        status_layout.addWidget(QLabel("Conexión:"), 0, 0)
        status_layout.addWidget(self.connection_status_label, 0, 1)
        status_layout.addWidget(QLabel("Seguimiento:"), 1, 0)
        status_layout.addWidget(self.tracking_status_label, 1, 1)
        status_layout.addWidget(QLabel("Objetos detectados:"), 2, 0)
        status_layout.addWidget(self.objects_count_label, 2, 1)
        status_layout.addWidget(QLabel("Objetivo actual:"), 3, 0)
        status_layout.addWidget(self.current_target_label, 3, 1)
        
        layout.addWidget(status_group)
        layout.addStretch()
        
        self.main_tabs.addTab(tab, "🎮 Control")

    def _create_config_tab(self):
        """Crear tab de configuración"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Scroll area para configuraciones
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # === CONFIGURACIÓN DE DETECCIÓN ===
        detection_group = QGroupBox("🔍 Configuración de Detección")
        detection_layout = QFormLayout(detection_group)
        
        self.confidence_threshold = QDoubleSpinBox()
        self.confidence_threshold.setRange(0.1, 1.0)
        self.confidence_threshold.setValue(0.5)
        self.confidence_threshold.setSingleStep(0.05)
        self.confidence_threshold.setDecimals(2)
        
        self.max_objects = QSpinBox()
        self.max_objects.setRange(1, 10)
        self.max_objects.setValue(3)
        
        detection_layout.addRow("Confianza mínima:", self.confidence_threshold)
        detection_layout.addRow("Máximo objetos:", self.max_objects)
        
        scroll_layout.addWidget(detection_group)
        
        # === CONFIGURACIÓN DE ALTERNANCIA ===
        alternating_group = QGroupBox("🔄 Configuración de Alternancia")
        alternating_layout = QFormLayout(alternating_group)
        
        self.switch_interval = QDoubleSpinBox()
        self.switch_interval.setRange(1.0, 30.0)
        self.switch_interval.setValue(5.0)
        self.switch_interval.setSuffix(" segundos")
        
        self.enable_alternating = QCheckBox("Habilitar alternancia automática")
        self.enable_alternating.setChecked(True)
        
        alternating_layout.addRow("Intervalo de cambio:", self.switch_interval)
        alternating_layout.addRow(self.enable_alternating)
        
        scroll_layout.addWidget(alternating_group)
        
        # === CONFIGURACIÓN DE ZOOM ===
        zoom_group = QGroupBox("🔍 Configuración de Zoom")
        zoom_layout = QFormLayout(zoom_group)
        
        self.enable_auto_zoom = QCheckBox("Habilitar zoom automático")
        self.enable_auto_zoom.setChecked(True)
        
        self.zoom_speed = QDoubleSpinBox()
        self.zoom_speed.setRange(0.1, 1.0)
        self.zoom_speed.setValue(0.3)
        self.zoom_speed.setSingleStep(0.1)
        self.zoom_speed.setDecimals(1)
        
        zoom_layout.addRow(self.enable_auto_zoom)
        zoom_layout.addRow("Velocidad de zoom:", self.zoom_speed)
        
        scroll_layout.addWidget(zoom_group)
        
        # === CONFIGURACIÓN DE PRIORIDADES ===
        priority_group = QGroupBox("⚖️ Pesos de Prioridad")
        priority_layout = QFormLayout(priority_group)
        
        self.confidence_weight = QDoubleSpinBox()
        self.confidence_weight.setRange(0.0, 1.0)
        self.confidence_weight.setValue(0.4)
        self.confidence_weight.setSingleStep(0.1)
        self.confidence_weight.setDecimals(1)
        
        self.movement_weight = QDoubleSpinBox()
        self.movement_weight.setRange(0.0, 1.0)
        self.movement_weight.setValue(0.3)
        self.movement_weight.setSingleStep(0.1)
        self.movement_weight.setDecimals(1)
        
        self.size_weight = QDoubleSpinBox()
        self.size_weight.setRange(0.0, 1.0)
        self.size_weight.setValue(0.2)
        self.size_weight.setSingleStep(0.1)
        self.size_weight.setDecimals(1)
        
        self.proximity_weight = QDoubleSpinBox()
        self.proximity_weight.setRange(0.0, 1.0)
        self.proximity_weight.setValue(0.1)
        self.proximity_weight.setSingleStep(0.1)
        self.proximity_weight.setDecimals(1)
        
        priority_layout.addRow("Peso confianza:", self.confidence_weight)
        priority_layout.addRow("Peso movimiento:", self.movement_weight)
        priority_layout.addRow("Peso tamaño:", self.size_weight)
        priority_layout.addRow("Peso proximidad:", self.proximity_weight)
        
        scroll_layout.addWidget(priority_group)
        scroll_layout.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        self.main_tabs.addTab(tab, "⚙️ Configuración")

    def _create_monitoring_tab(self):
        """Crear tab de monitoreo en tiempo real"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # === OBJETOS DETECTADOS ===
        objects_group = QGroupBox("🎯 Objetos Detectados")
        objects_layout = QVBoxLayout(objects_group)
        
        self.objects_table = QTableWidget()
        self.objects_table.setColumnCount(4)
        self.objects_table.setHorizontalHeaderLabels(["ID", "Tipo", "Confianza", "Estado"])
        
        # Configurar tabla
        header = self.objects_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        
        objects_layout.addWidget(self.objects_table)
        layout.addWidget(objects_group)
        
        # === LOG DEL SISTEMA ===
        log_group = QGroupBox("📝 Log del Sistema")
        log_layout = QVBoxLayout(log_group)
        
        self.status_display = QTextEdit()
        self.status_display.setMaximumHeight(200)
        self.status_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                border: 1px solid #555555;
                border-radius: 5px;
            }
        """)
        
        # Controles del log
        log_controls = QHBoxLayout()
        
        self.auto_scroll_checkbox = QCheckBox("Auto-scroll")
        self.auto_scroll_checkbox.setChecked(True)
        
        clear_log_btn = QPushButton("🗑️ Limpiar Log")
        clear_log_btn.clicked.connect(self.status_display.clear)
        
        log_controls.addWidget(self.auto_scroll_checkbox)
        log_controls.addStretch()
        log_controls.addWidget(clear_log_btn)
        
        log_layout.addWidget(self.status_display)
        log_layout.addLayout(log_controls)
        
        layout.addWidget(log_group)
        
        self.main_tabs.addTab(tab, "📊 Monitoreo")

    def _create_stats_tab(self):
        """Crear tab de estadísticas"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # === ESTADÍSTICAS DE RENDIMIENTO ===
        stats_group = QGroupBox("📈 Estadísticas de Rendimiento")
        stats_layout = QGridLayout(stats_group)
        
        # Labels para estadísticas
        self.session_time_label = QLabel("00:00:00")
        self.total_detections_label = QLabel("0")
        self.success_rate_label = QLabel("0.0%")
        self.moves_count_label = QLabel("0/0")
        self.switches_count_label = QLabel("0")
        
        stats_layout.addWidget(QLabel("Tiempo de sesión:"), 0, 0)
        stats_layout.addWidget(self.session_time_label, 0, 1)
        stats_layout.addWidget(QLabel("Total detecciones:"), 1, 0)
        stats_layout.addWidget(self.total_detections_label, 1, 1)
        stats_layout.addWidget(QLabel("Tasa de éxito:"), 2, 0)
        stats_layout.addWidget(self.success_rate_label, 2, 1)
        stats_layout.addWidget(QLabel("Movimientos (éxito/total):"), 3, 0)
        stats_layout.addWidget(self.moves_count_label, 3, 1)
        stats_layout.addWidget(QLabel("Cambios de objetivo:"), 4, 0)
        stats_layout.addWidget(self.switches_count_label, 4, 1)
        
        layout.addWidget(stats_group)
        
        # === GRÁFICO DE RENDIMIENTO (placeholder) ===
        chart_group = QGroupBox("📊 Rendimiento en Tiempo Real")
        chart_layout = QVBoxLayout(chart_group)
        
        # Placeholder para gráfico
        chart_placeholder = QLabel("📊 Gráfico de rendimiento\n(Implementar con matplotlib)")
        chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chart_placeholder.setStyleSheet("""
            QLabel {
                border: 2px dashed #555555;
                border-radius: 10px;
                padding: 20px;
                color: #888888;
                font-size: 14px;
            }
        """)
        chart_placeholder.setMinimumHeight(200)
        
        chart_layout.addWidget(chart_placeholder)
        layout.addWidget(chart_group)
        
        layout.addStretch()
        
        self.main_tabs.addTab(tab, "📈 Estadísticas")

    def _connect_all_signals(self):
        """Conectar todas las señales de la interfaz"""
        # Controles principales
        self.start_btn.clicked.connect(self._start_tracking)
        self.stop_btn.clicked.connect(self._stop_tracking)
        
        # Selectores
        self.camera_selector.currentIndexChanged.connect(self._on_camera_changed)
        self.tracking_mode_selector.currentTextChanged.connect(self._on_mode_changed)
        
        # Configuración
        self.confidence_threshold.valueChanged.connect(self._on_config_changed)
        self.switch_interval.valueChanged.connect(self._on_config_changed)
        self.enable_alternating.stateChanged.connect(self._on_config_changed)

    def _apply_dark_theme(self):
        """Aplicar tema oscuro moderno"""
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555555;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #3b3b3b;
            }
            QTabBar::tab {
                background-color: #555555;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #3b3b3b;
                border-bottom: 2px solid #007bff;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #555555;
                color: #ffffff;
                border: 1px solid #777777;
                border-radius: 3px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QCheckBox {
                color: #ffffff;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #555555;
                border: 1px solid #777777;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #007bff;
                border: 1px solid #007bff;
                border-radius: 3px;
            }
            QTableWidget {
                background-color: #3b3b3b;
                color: #ffffff;
                border: 1px solid #555555;
                gridline-color: #555555;
            }
            QHeaderView::section {
                background-color: #555555;
                color: #ffffff;
                border: 1px solid #777777;
                padding: 5px;
            }
        """)

    def _load_camera_configuration(self):
        """Cargar configuración de cámaras"""
        try:
            # Esta función se puede expandir para cargar configuraciones específicas
            self._log("📁 Configuración de cámaras cargada")
        except Exception as e:
            self._log(f"⚠️ Error cargando configuración de cámaras: {e}")

    def _load_ui_configuration(self):
        """Cargar configuración de la interfaz"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                
                # Aplicar configuración guardada
                if 'confidence_threshold' in config:
                    self.confidence_threshold.setValue(config['confidence_threshold'])
                if 'switch_interval' in config:
                    self.switch_interval.setValue(config['switch_interval'])
                if 'tracking_mode' in config:
                    self.tracking_mode_selector.setCurrentText(config['tracking_mode'])
                
                self._log("📁 Configuración de UI cargada")
        except Exception as e:
            self._log(f"⚠️ Error cargando configuración de UI: {e}")

    def _save_ui_configuration(self):
        """Guardar configuración de la interfaz"""
        try:
            config = {
                'confidence_threshold': self.confidence_threshold.value(),
                'switch_interval': self.switch_interval.value(),
                'tracking_mode': self.tracking_mode_selector.currentText(),
                'enable_alternating': self.enable_alternating.isChecked(),
                'enable_auto_zoom': self.enable_auto_zoom.isChecked(),
                'last_saved': datetime.now().isoformat()
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
                
            self._log("💾 Configuración de UI guardada")
        except Exception as e:
            self._log(f"⚠️ Error guardando configuración: {e}")

    def _log(self, message):
        """Agregar mensaje al log del sistema"""
        if hasattr(self, 'status_display'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            self.status_display.append(formatted_message)
            
            if hasattr(self, 'auto_scroll_checkbox') and self.auto_scroll_checkbox.isChecked():
                self.status_display.ensureCursorVisible()

    def _start_tracking(self):
        """Iniciar seguimiento PTZ multi-objeto - VERSIÓN CORREGIDA"""
        try:
            camera_data = self.get_current_camera_data()
            if not camera_data:
                raise Exception("No hay datos de cámara disponibles")

            # CORRECCIÓN 1: Activar flag antes de crear el tracker
            self.tracking_active = True

            self._log("🚀 Iniciando seguimiento PTZ multi-objeto...")

            # Verificar sistema multi-objeto
            if MULTI_OBJECT_AVAILABLE:
                ip = camera_data.get('ip')
                port = camera_data.get('puerto', 80)
                username = camera_data.get('usuario')
                password = camera_data.get('contrasena')

                self._log(f"📡 Conectando a cámara: {ip}:{port} (usuario: {username})")

                # CORRECCIÓN 2: Crear tracker con verificación
                self.current_tracker = MultiObjectPTZTracker(
                    ip=ip,
                    port=port,
                    username=username,
                    password=password,
                    multi_config=self.multi_config,
                )

                if self.current_tracker:
                    # CORRECCIÓN 3: solo verificar conexión
                    try:
                        connection_ok = self.current_tracker._test_ptz_connection()
                        if not connection_ok:
                            raise Exception("Error de conexión PTZ")
                        self._log("✅ Conexión PTZ verificada")
                    except Exception as e:
                        self._log(f"⚠️ Advertencia conexión PTZ: {e}")
                else:
                    raise Exception("No se pudo crear el tracker PTZ")
            else:
                raise Exception("Sistema multi-objeto no disponible")

            # CORRECCIÓN 4: Configurar UI después de inicializar tracker
            self.session_start_time = time.time()
            self.detection_count = 0

            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.system_status_label.setText("🟢 Sistema Activo")
            self.system_status_label.setStyleSheet(
                """
            QLabel {
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 15px;
                background-color: #1b2d1b;
                color: #28a745;
            }
            """
            )

            # CORRECCIÓN 5: Iniciar hilo de estado solo si hay tracker
            if self.current_tracker:
                self.status_thread = StatusUpdateThread(self.current_tracker)
                self.status_thread.status_updated.connect(self._update_status_display)
                self.status_thread.error_occurred.connect(self._handle_status_error)
                self.status_thread.start()
                self._log("✅ Hilo de estado iniciado")

            self._log("✅ Seguimiento PTZ multi-objeto iniciado exitosamente")

            # CORRECCIÓN 6: Emitir señal después de todo configurado
            self.tracking_started.emit()

        except Exception as e:
            self._log(f"❌ Error iniciando seguimiento: {e}")
            self._reset_ui_to_inactive()
            # Solo loguear, no mostrar QMessageBox
            self._log("💡 Verifique conexión y configuración de cámara")

    def _stop_tracking(self):
        """Detener seguimiento PTZ multi-objeto - MÉTODO CORREGIDO"""
        try:
            self._log("🛑 Deteniendo seguimiento PTZ...")
            
            # === DETENER HILO DE ESTADO PRIMERO ===
            if hasattr(self, 'status_thread') and self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)  # Esperar máximo 2 segundos
                self.status_thread = None
                self._log("✅ Hilo de estado detenido")
            
            # Detener tracker
            if self.current_tracker:
                self.current_tracker.stop_tracking()
                self.current_tracker = None
                self._log("✅ Tracker PTZ detenido")
            
            # Resetear UI
            self._reset_ui_to_inactive()
            
            self._log("✅ Seguimiento PTZ detenido exitosamente")
            self.tracking_stopped.emit()
            
        except Exception as e:
            self._log(f"❌ Error deteniendo seguimiento: {e}")
            # Forzar reset de UI incluso con errores
            self._reset_ui_to_inactive()

    def _reset_ui_to_inactive(self):
        """Resetear UI a estado inactivo"""
        self.tracking_active = False
        self.session_start_time = 0
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.system_status_label.setText("🔴 Sistema Inactivo")
        self.system_status_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 15px;
                background-color: #2d1b1b;
                color: #dc3545;
            }
        """)

    def _update_status_display(self, status):
        """Actualizar display de estado - CORREGIDO"""
        try:
            # VERIFICACIÓN CRÍTICA: asegurar que status es un diccionario
            if not isinstance(status, dict):
                self._log(f"⚠️ Status inválido recibido: {type(status)}")
                status = {
                    'tracking_active': self.tracking_active,
                    'camera_connected': False,
                    'current_target': None,
                    'object_count': 0,
                    'ptz_moving': False
                }

            camera_connected = False

            if self.current_tracker and hasattr(self.current_tracker, 'camera'):
                try:
                    camera_connected = (self.current_tracker.camera is not None and
                                       hasattr(self.current_tracker, 'ptz_service') and
                                       self.current_tracker.ptz_service is not None)
                except:
                    camera_connected = False

            if self.tracking_active and self.current_tracker:
                camera_connected = True

            if hasattr(self, 'connection_status_label'):
                if camera_connected:
                    self.connection_status_label.setText("🟢 Conectado")
                    self.connection_status_label.setStyleSheet("color: #28a745;")
                else:
                    self.connection_status_label.setText("🔴 Desconectado")
                    self.connection_status_label.setStyleSheet("color: #dc3545;")

            if hasattr(self, 'tracking_status_label'):
                if self.tracking_active:
                    self.tracking_status_label.setText("🟢 Activo")
                    self.tracking_status_label.setStyleSheet("color: #28a745;")
                else:
                    self.tracking_status_label.setText("🔴 Inactivo")
                    self.tracking_status_label.setStyleSheet("color: #dc3545;")

            object_count = status.get('object_count', 0)
            current_target = status.get('current_target')

            if hasattr(self, 'objects_detected_label'):
                self.objects_detected_label.setText(str(object_count))

            if hasattr(self, 'current_target_label'):
                if current_target is not None:
                    is_primary = status.get('is_primary', True)
                    target_text = f"{{'id': {current_target}, 'is_primary': {is_primary}}}"
                    self.current_target_label.setText(target_text)
                else:
                    self.current_target_label.setText("{'id': None, 'is_primary': True}")

        except Exception as e:
            self._log(f"❌ Error actualizando display de estado: {e}")

    def _handle_status_error(self, error_message):
        """Manejar errores del hilo de estado - MÉTODO AGREGADO"""
        self._log(f"⚠️ Error en hilo de estado: {error_message}")
        
        # Si hay demasiados errores, detener tracking
        if "Demasiados errores" in error_message or "máximo" in error_message.lower():
            self._log("🛑 Deteniendo seguimiento por errores críticos en hilo de estado")
            self._stop_tracking()

    def _update_ui_displays(self):
        """Actualizar displays de la UI cada segundo"""
        if self.tracking_active and self.session_start_time > 0:
            # Calcular tiempo de sesión
            elapsed = time.time() - self.session_start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            if hasattr(self, 'tracking_time_label'):
                self.tracking_time_label.setText(f"⏱️ {time_str}")
            if hasattr(self, 'session_time_label'):
                self.session_time_label.setText(time_str)

    def _on_camera_changed(self, index):
        """Manejar cambio de cámara seleccionada"""
        if index > 0:  # Ignorar "Seleccionar cámara..."
            camera_data = self.camera_selector.currentData()
            self.current_camera_data = camera_data
            self.current_camera_id = camera_data.get('id') if camera_data else None
            
            camera_name = camera_data.get('nombre', camera_data.get('ip', 'Sin nombre'))
            self._log(f"📹 Cámara seleccionada: {camera_name}")
            
            if hasattr(self, 'camera_status_label'):
                self.camera_status_label.setText(f"📷 {camera_name}")

    def get_current_camera_data(self):
        """Obtener datos de la cámara actualmente seleccionada"""
        if hasattr(self, 'current_camera_data') and self.current_camera_data:
            return self.current_camera_data
        if hasattr(self, 'camera_selector'):
            return self.camera_selector.currentData()
        return None

    def _on_mode_changed(self, mode_text):
        """Manejar cambio de modo de seguimiento"""
        if MULTI_OBJECT_AVAILABLE and self.multi_config:
            mode_map = {
                "Objeto Individual": TrackingMode.SINGLE_OBJECT,
                "Multi-Objeto Alternante": TrackingMode.MULTI_OBJECT_ALTERNATING,
                "Basado en Prioridad": TrackingMode.MULTI_OBJECT_PRIORITY,
                "Cambio Automático": TrackingMode.AUTO_SWITCH
            }
            
            if mode_text in mode_map:
                self.multi_config.tracking_mode = mode_map[mode_text]
                self._log(f"🎯 Modo de seguimiento: {mode_text}")

    def _on_config_changed(self):
        """Manejar cambios en configuración"""
        if MULTI_OBJECT_AVAILABLE and self.multi_config:
            # Actualizar configuración del sistema
            self.multi_config.min_confidence_threshold = self.confidence_threshold.value()
            self.multi_config.primary_follow_time = self.switch_interval.value()
            self.multi_config.alternating_enabled = self.enable_alternating.isChecked()
            
            # Actualizar pesos de prioridad
            self.multi_config.confidence_weight = self.confidence_weight.value()
            self.multi_config.movement_weight = self.movement_weight.value()
            self.multi_config.size_weight = self.size_weight.value()
            self.multi_config.proximity_weight = self.proximity_weight.value()
            
            self._log("⚙️ Configuración actualizada")

    def _show_error_dialog(self):
        """Mostrar diálogo de error cuando no hay sistemas disponibles"""
        error_msg = """
❌ Sistema PTZ Multi-Objeto No Disponible

Los módulos requeridos no están disponibles:

• core/multi_object_ptz_system.py
• core/ptz_tracking_integration_enhanced.py
• core/ptz_control.py

Por favor, verifique la instalación de los módulos PTZ.
        """
        
        QMessageBox.critical(self, "Error del Sistema", error_msg.strip())
        self.close()


    def update_detections(self, detections: list, frame_size: tuple = (1920, 1080)):
        """Actualizar detecciones para seguimiento - MÉTODO CORREGIDO"""
        try:
            # Verificar estado del seguimiento
            if not hasattr(self, 'tracking_active') or not self.tracking_active:
                return False

            if not hasattr(self, 'current_tracker') or not self.current_tracker:
                return False

            # Validar detecciones
            if not isinstance(detections, list) or not detections:
                return False

            valid_detections = []
            for det in detections:
                if isinstance(det, dict) and 'bbox' in det and len(det.get('bbox', [])) == 4:
                    valid_detections.append(det)

            if not valid_detections:
                return False

            # Incrementar contador de detecciones
            if not hasattr(self, 'detection_count'):
                self.detection_count = 0
            self.detection_count += len(valid_detections)

            # Loguear solo las primeras detecciones para evitar spam
            if self.detection_count <= 50:
                self._log(f"📊 Procesando {len(valid_detections)} detecciones (total: {self.detection_count})")

            # CORRECCIÓN CRÍTICA: Intentar múltiples métodos de seguimiento
            success = False

            # Método 1: update_tracking
            if hasattr(self.current_tracker, 'update_tracking'):
                try:
                    success = self.current_tracker.update_tracking(valid_detections, frame_size)
                except Exception as e:
                    self._log(f"❌ Error en update_tracking: {e}")

            # Método 2: track_objects (si el anterior falló)
            if not success and hasattr(self.current_tracker, 'track_objects'):
                try:
                    success = self.current_tracker.track_objects(valid_detections, frame_size)
                except Exception as e:
                    self._log(f"❌ Error en track_objects: {e}")

            # Método 3: process_detections (último recurso)
            if not success and hasattr(self.current_tracker, 'process_detections'):
                try:
                    success = self.current_tracker.process_detections(valid_detections, frame_size)
                except Exception as e:
                    self._log(f"❌ Error en process_detections: {e}")

            # Si ningún método funcionó, mostrar error solo una vez cada 10 intentos
            if not success:
                if not hasattr(self, '_tracking_error_count'):
                    self._tracking_error_count = 0
                self._tracking_error_count += 1

                if self._tracking_error_count % 10 == 1:  # Solo cada 10 errores
                    self._log("⚠️ Método de seguimiento no encontrado en tracker")

            return success

        except Exception as e:
            self._log(f"❌ Error procesando detecciones: {e}")
            return False

    def set_detection_bridge(self, bridge):
        """Establecer el bridge de detecciones"""
        self.detection_bridge = bridge
        self._log("🌉 Bridge de detecciones configurado")
# Función de creación del sistema completo
def create_multi_object_ptz_system(camera_list, parent=None):
    """Crear sistema PTZ multi-objeto completo con bridge de integración"""
    try:
        # Crear diálogo principal
        dialog = EnhancedMultiObjectPTZDialog(parent, camera_list)
        
        # Crear bridge de integración (clase completa para conectar con el sistema principal)
        class PTZDetectionBridge:
            """Puente de integración PTZ CORREGIDO"""

            def __init__(self, dialog):
                self.dialog = dialog
                self.active_cameras = {}
                self.detection_count = 0

            def send_detections(self, camera_id: str, detections: list, frame_size=(1920, 1080)):
                """Enviar detecciones al sistema PTZ - FIRMA CORREGIDA"""
                # Nota: camera_id debe ser el primer parámetro para evitar
                # confusiones con el orden original (detections, frame_size)
                try:
                    # Validar parámetros
                    if not isinstance(camera_id, str):
                        print(f"❌ camera_id debe ser string, recibido: {type(camera_id)}")
                        return False

                    if not isinstance(detections, list):
                        print(f"❌ detections debe ser lista, recibido: {type(detections)}")
                        return False

                    if (not isinstance(frame_size, (tuple, list)) or
                            len(frame_size) != 2):
                        print(f"❌ frame_size inválido: {frame_size}")
                        return False

                    # Solo procesar si el diálogo está activo
                    if self.dialog and self.dialog.tracking_active:
                        # Debug log
                        print(f"🔄 PTZ Bridge: enviando {len(detections)} detecciones para cámara {camera_id}")

                        # Llamar al método update_detections del diálogo
                        self.dialog.update_detections(detections, frame_size)

                        # Actualizar estadísticas
                        self.detection_count += len(detections)
                        if camera_id not in self.active_cameras:
                            self.active_cameras[camera_id] = {'detections_sent': 0}
                        self.active_cameras[camera_id]['detections_sent'] += len(detections)

                        return True
                    else:
                        print(f"⚠️ PTZ Bridge: diálogo no activo para cámara {camera_id}")
                        return False

                except Exception as e:
                    print(f"❌ Error en PTZ Bridge.send_detections: {e}")
                    return False

            def register_camera(self, camera_id: str, camera_data: dict):
                """Registrar una cámara en el bridge"""
                try:
                    self.active_cameras[camera_id] = {
                        'data': camera_data,
                        'detections_sent': 0,
                        'registered_at': __import__('time').time()
                    }
                    print(f"📷 Cámara registrada en PTZ Bridge: {camera_id}")
                    return True
                except Exception as e:
                    print(f"❌ Error registrando cámara en PTZ Bridge: {e}")
                    return False

            def get_status(self, camera_id: str = None):
                """Obtener estado del bridge"""
                try:
                    status = {
                        'active': self.dialog.tracking_active if self.dialog else False,
                        'total_detections': self.detection_count,
                        'cameras_count': len(self.active_cameras),
                        'cameras': list(self.active_cameras.keys())
                    }

                    if camera_id and camera_id in self.active_cameras:
                        status['camera_info'] = self.active_cameras[camera_id]

                    return status
                except Exception as e:
                    return {'error': str(e)}

            def cleanup(self):
                """Limpiar recursos del bridge"""
                self.active_cameras.clear()
                self.detection_count = 0
                print("🧹 PTZ Bridge limpiado")
        
        bridge = PTZDetectionBridge(dialog)
        
        return dialog, bridge
        
    except Exception as e:
        print(f"❌ Error creando sistema PTZ multi-objeto: {e}")
        return None, None

# === IMPLEMENTACIÓN DE FUNCIONES Y CLASES ADICIONALES CORREGIDAS ===

class PTZDetectionBridge:
    """Bridge CORREGIDO para conectar detecciones con PTZ"""

    def __init__(self, ptz_system):
        self.ptz_system = ptz_system
        self.active_cameras = {}
        self.detection_count = 0

    def send_detections(self, camera_id: str, detections: list, frame_size=(1920, 1080)):
        """Enviar detecciones al sistema PTZ - MÉTODO CORREGIDO"""
        try:
            # CORRECCIÓN 12: Verificar que el diálogo exista Y esté activo
            if not hasattr(self.ptz_system, 'dialog') or not self.ptz_system.dialog:
                print(f"⚠️ PTZ Bridge: no hay diálogo para cámara {camera_id}")
                return False

            dialog = self.ptz_system.dialog

            # CORRECCIÓN 13: Verificar tracking_active correctamente
            if not hasattr(dialog, 'tracking_active') or not dialog.tracking_active:
                print(f"⚠️ PTZ Bridge: diálogo no activo para cámara {camera_id}")
                return False

            # Validar detecciones
            if not isinstance(detections, list) or not detections:
                return False

            valid_detections = []
            for det in detections:
                if isinstance(det, dict) and 'bbox' in det:
                    valid_detections.append(det)

            if not valid_detections:
                return False

            # CORRECCIÓN 14: Llamar a update_detections del diálogo
            success = dialog.update_detections(valid_detections, frame_size)

            if success:
                # Actualizar estadísticas
                self.detection_count += len(valid_detections)
                if camera_id not in self.active_cameras:
                    self.active_cameras[camera_id] = {'detections_sent': 0}
                self.active_cameras[camera_id]['detections_sent'] += len(valid_detections)

                return True
            else:
                return False

        except Exception as e:
            print(f"❌ Error en PTZ Bridge.send_detections: {e}")
            return False

    def register_camera(self, camera_id: str, camera_data: dict):
        """Registrar una cámara en el bridge"""
        try:
            self.active_cameras[camera_id] = {
                'data': camera_data,
                'detections_sent': 0,
                'registered_at': time.time()
            }
            print(f"📷 Cámara registrada en PTZ Bridge: {camera_id}")
            return True
        except Exception as e:
            print(f"❌ Error registrando cámara en PTZ Bridge: {e}")
            return False


def create_enhanced_ptz_system_fixed(parent, camera_list):
    """Crear sistema PTZ multi-objeto CORREGIDO"""
    try:
        # Crear diálogo
        dialog = EnhancedMultiObjectPTZDialog(parent, camera_list)

        # CORRECCIÓN 16: Configurar el bridge correctamente
        class PTZSystemWrapper:
            def __init__(self, dialog):
                self.dialog = dialog

        # Crear wrapper del sistema
        ptz_system = PTZSystemWrapper(dialog)

        # Crear bridge
        bridge = PTZDetectionBridge(ptz_system)

        # CORRECCIÓN 17: Conectar bridge al diálogo
        dialog.detection_bridge = bridge

        print("✅ Sistema PTZ multi-objeto CORREGIDO creado")

        return {
            'dialog': dialog,
            'bridge': bridge,
            'system': ptz_system
        }

    except Exception as e:
        print(f"❌ Error creando sistema PTZ corregido: {e}")
        return None


def ensure_ptz_tracking_active(main_window):
    """Asegurar que el seguimiento PTZ esté activo"""
    try:
        if not hasattr(main_window, 'ptz_detection_bridge'):
            print("⚠️ PTZ Bridge no disponible")
            return False

        bridge = main_window.ptz_detection_bridge
        if not bridge or not hasattr(bridge, 'ptz_system'):
            print("⚠️ Sistema PTZ no configurado")
            return False

        dialog = bridge.ptz_system.dialog
        if not dialog:
            print("⚠️ Diálogo PTZ no disponible")
            return False

        # CORRECCIÓN 19: Forzar activación si no está activo
        if not getattr(dialog, 'tracking_active', False):
            print("🔄 Activando seguimiento PTZ...")

            dialog.tracking_active = True

            if hasattr(dialog, 'start_btn'):
                dialog.start_btn.setEnabled(False)
            if hasattr(dialog, 'stop_btn'):
                dialog.stop_btn.setEnabled(True)
            if hasattr(dialog, 'system_status_label'):
                dialog.system_status_label.setText("🟢 Sistema Activo")

            print("✅ Seguimiento PTZ activado manualmente")

        return True

    except Exception as e:
        print(f"❌ Error activando seguimiento PTZ: {e}")
        return False

if __name__ == "__main__":
    # Ejecutar diálogo de forma independiente para pruebas
    app = QApplication(sys.argv)
    
    # Datos de cámaras de prueba
    test_cameras = [
        {
            'ip': '192.168.1.100',
            'tipo': 'ptz',
            'nombre': 'PTZ Cámara 1',
            'usuario': 'admin',
            'contrasena': 'admin123'
        },
        {
            'ip': '192.168.1.101',
            'tipo': 'ptz',
            'nombre': 'PTZ Cámara 2',
            'usuario': 'admin',
            'contrasena': 'admin123'
        }
    ]
    
    dialog, bridge = create_multi_object_ptz_system(test_cameras)
    
    if dialog:
        dialog.show()
        
        # Simular detecciones de prueba cada 2 segundos
        def simulate_detections():
            import random
            detections = []
            for i in range(random.randint(1, 3)):
                detection = {
                    'bbox': [
                        random.randint(100, 800),
                        random.randint(100, 600),
                        random.randint(900, 1200),
                        random.randint(700, 900)
                    ],
                    'confidence': random.uniform(0.6, 0.95),
                    'class': random.choice(['person', 'boat', 'vehicle'])
                }
                detections.append(detection)
            
            if bridge:
                bridge.send_detections('test_camera', detections)
        
        # Timer para simulación
        timer = QTimer()
        timer.timeout.connect(simulate_detections)
        timer.start(2000)  # Cada 2 segundos
        
        sys.exit(app.exec())
    else:
        print("❌ No se pudo crear el diálogo PTZ")
