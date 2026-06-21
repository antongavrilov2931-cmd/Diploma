import sys
import random

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QFrame
)

from PyQt5.QtCore import Qt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from radar_scene import RadarWidget

class StatCard(QFrame):

    def __init__(self, title, value):

        super().__init__()

        self.setStyleSheet("""
            background:#1e293b;
            border-radius:12px;
        """)

        layout = QVBoxLayout()

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)

        self.value_lbl = QLabel(str(value))
        self.value_lbl.setAlignment(Qt.AlignCenter)

        self.value_lbl.setStyleSheet("""
            font-size:28px;
            font-weight:bold;
            color:#38bdf8;
        """)

        layout.addWidget(title_lbl)
        layout.addWidget(self.value_lbl)

        self.setLayout(layout)

    def set_value(self, value):
        self.value_lbl.setText(str(value))
class DashboardTab(QWidget):

    def __init__(self):

        super().__init__()

        layout = QVBoxLayout()

        cards = QHBoxLayout()

        self.total = StatCard(
            "Всего целей",
            3
        )

        self.detected = StatCard(
            "Обнаружено",
            2
        )

        self.lost = StatCard(
            "Потеряно",
            1
        )

        self.prob = StatCard(
            "Pобн",
            "66%"
        )

        cards.addWidget(self.total)
        cards.addWidget(self.detected)
        cards.addWidget(self.lost)
        cards.addWidget(self.prob)

        layout.addLayout(cards)

        self.setLayout(layout)

class RadarTab(QWidget):

    def __init__(self):

        super().__init__()

        layout = QVBoxLayout()

        self.radar_widget = RadarWidget()

        layout.addWidget(
            self.radar_widget
        )

        self.setLayout(layout)

class AnalyticsTab(QWidget):

    def __init__(self):

        super().__init__()

        layout = QVBoxLayout()

        fig = Figure(
            figsize=(6, 4)
        )

        canvas = FigureCanvasQTAgg(fig)

        ax = fig.add_subplot(111)

        labels = [
            "Обнаружено",
            "Потеряно",
            "Активные"
        ]

        values = [
            2,
            1,
            3
        ]

        ax.bar(
            labels,
            values,
            color=[
                "green",
                "red",
                "cyan"
            ]
        )

        ax.set_title(
            "Статистика целей"
        )

        layout.addWidget(canvas)

        self.setLayout(layout)

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "Система управления ресурсами РЛК"
        )

        self.resize(
            1400,
            900
        )

        tabs = QTabWidget()

        tabs.addTab(
            DashboardTab(),
            "Dashboard"
        )

        tabs.addTab(
            RadarTab(),
            "Радиолокационная обстановка"
        )

        tabs.addTab(
            AnalyticsTab(),
            "Аналитика"
        )

        self.setCentralWidget(
            tabs
        )
if __name__ == "__main__":

    app = QApplication(sys.argv)

    app.setStyleSheet("""

        QWidget{
            background:#0f172a;
            color:white;
            font-size:14px;
        }

        QTabBar::tab{
            background:#1e293b;
            padding:12px;
            min-width:180px;
        }

        QTabBar::tab:selected{
            background:#2563eb;
        }

    """)

    window = MainWindow()

    window.show()

    sys.exit(app.exec_())