"""Yula'nın sakin, koyu ve tek vurgulu masaüstü tasarım sistemi."""

BACKGROUND = "#121316"
SURFACE = "#1A1C20"
SURFACE_RAISED = "#202329"
BORDER = "#272A30"
TEXT = "#F0F2F5"
MUTED_TEXT = "#8E96A3"
ACCENT = "#388BFD"

STATUS_STYLES = {
    "WAITING": (MUTED_TEXT, BORDER),
    "PREPARING": (TEXT, "#46515C"),
    "RUNNING": (ACCENT, ACCENT),
    "STOPPED": (MUTED_TEXT, BORDER),
    "ERROR": ("#D7DCE1", "#68717A"),
}

RISK_STYLES = {
    "HIGH": ("#FF6B6B", "rgba(255, 107, 107, 38)"),
    "MEDIUM": ("#F5A524", "rgba(245, 165, 36, 38)"),
    "LOW": ("#57C78B", "rgba(87, 199, 139, 38)"),
}


def status_dot_stylesheet(status: str) -> str:
    foreground, _border = STATUS_STYLES[status]
    return f"""
        QLabel {{
            background-color: {foreground};
            border: none;
            border-radius: 3px;
        }}
    """


def risk_badge_stylesheet(risk: str) -> str:
    foreground, background = RISK_STYLES.get(
        risk,
        (MUTED_TEXT, "rgba(142, 150, 163, 38)"),
    )
    return (
        f"color: {foreground}; background-color: {background}; "
        "border: 1px solid transparent; border-radius: 10px; "
        "padding: 3px 9px; font-size: 11px; font-weight: 500;"
    )


APPLICATION_STYLESHEET = f"""
    QMainWindow, QDialog, QWidget#centralWidget {{
        background-color: {BACKGROUND};
        color: {TEXT};
    }}
    QWidget {{ color: {TEXT}; font-size: 12px; font-weight: 400; }}
    QLabel#brandMark {{ background: transparent; }}
    QLabel#applicationTitle {{
        color: {TEXT}; font-size: 15px; font-weight: 600;
    }}
    QLabel#applicationSubtitle,
    QLabel#dialogDescription,
    QLabel#sectionDescription {{
        color: {MUTED_TEXT}; font-size: 12px; font-weight: 400;
    }}
    QLabel#dialogTitle {{
        color: {TEXT}; font-size: 15px; font-weight: 600;
    }}

    QLabel#headerBreadcrumb {{
        color: #858E9B; font-size: 11px; font-weight: 400;
    }}
    QFrame#unifiedToolbar {{
        background-color: #16181C;
        border: 1px solid {BORDER};
        border-radius: 9px;
    }}
    QLabel#sectionCaption {{
        color: {MUTED_TEXT}; font-size: 11px; font-weight: 500;
    }}
    QLabel#sectionTitle {{
        color: {TEXT}; font-size: 15px; font-weight: 600;
    }}
    QLabel#sessionLabel, QLabel#footerLabel {{
        color: {MUTED_TEXT}; font-size: 11px;
    }}
    QLabel#sidebarStatusLabel {{
        color: #AAB2B9; font-size: 10px; font-weight: 500;
    }}

    QPushButton {{
        color: #CDD3D8;
        background-color: transparent;
        border: 1px solid #3A4148;
        border-radius: 6px;
        min-height: 30px;
        padding: 2px 14px;
        font-weight: 400;
    }}
    QPushButton:hover {{
        color: {TEXT}; background-color: #1D2226; border-color: #59636C;
    }}
    QPushButton:pressed {{ background-color: #23292E; }}
    QPushButton:disabled {{ color: #555E66; border-color: #292E33; }}
    QPushButton#primaryButton {{
        color: {ACCENT}; background-color: transparent;
        border-color: {ACCENT}; font-weight: 500;
    }}
    QPushButton#primaryButton:hover {{
        color: #EAF6FF; background-color: #102B3E;
    }}
    QPushButton#dangerButton {{ color: #AAB1B8; border-color: #454C53; }}
    QPushButton#reportButton {{
        color: #AAB2BE; border: none;
        padding-left: 10px; padding-right: 10px;
    }}
    QPushButton#sessionsButton {{
        color: #AAB2BA; border: none;
        padding-left: 10px; padding-right: 10px;
    }}
    QPushButton#sessionsButton:checked {{
        color: {ACCENT}; background-color: transparent;
        border-bottom: 1px solid {ACCENT};
    }}
    QToolButton#eventFilterButton, QToolButton#refreshButton {{
        color: #89939C;
        background-color: transparent;
        border: none;
        border-radius: 6px;
        min-width: 30px;
        min-height: 30px;
        padding: 0;
    }}
    QToolButton#eventFilterButton:hover, QToolButton#refreshButton:hover {{
        background-color: #1D2226;
        border: 1px solid #343943;
    }}
    QToolButton#eventFilterButton::menu-indicator {{ image: none; }}
    QToolButton#refreshButton {{
        color: #85909D; font-size: 18px; font-weight: 400;
    }}
    QToolButton#liveFollowButton {{
        color: {MUTED_TEXT}; background: transparent;
        border: 1px solid {BORDER}; border-radius: 10px;
        min-height: 24px; padding: 0 9px; font-size: 11px;
    }}
    QToolButton#liveFollowButton:checked {{
        color: {ACCENT}; background-color: rgba(56, 139, 253, 28);
        border-color: rgba(56, 139, 253, 90);
    }}
    QMenu {{
        color: #C7CDD3;
        background-color: {SURFACE_RAISED};
        border: 1px solid #3A4148;
        padding: 5px;
    }}
    QMenu::item {{ padding: 7px 24px 7px 9px; }}
    QMenu::item:selected {{ background-color: #222A31; color: {TEXT}; }}
    QMenu::indicator:checked {{
        width: 5px; height: 5px;
        background-color: {ACCENT};
    }}

    QTabBar#eventViewTabs {{
        background-color: #121418;
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    QTabBar#eventViewTabs::tab {{
        color: #7F8992;
        background-color: transparent;
        border: none;
        border-radius: 6px;
        padding: 6px 10px;
        margin: 2px;
        font-size: 11px;
        font-weight: 400;
    }}
    QTabBar#eventViewTabs::tab:selected {{
        color: {TEXT}; background-color: #2C313A;
    }}
    QTabBar#eventViewTabs::tab:hover {{
        color: #C8CED4; background-color: #20242A;
    }}

    QLineEdit, QComboBox, QDateTimeEdit {{
        min-height: 30px;
        color: #D8DDE2;
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 0 9px;
        selection-background-color: #164A70;
    }}
    QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus {{
        border-color: {ACCENT};
    }}
    QComboBox QAbstractItemView {{
        color: #D8DDE2; background-color: {SURFACE_RAISED};
        border: 1px solid #3A4148; selection-background-color: #243847;
    }}

    QTreeWidget#eventTree {{
        color: #D7DCE1; font-size: 12px;
        background-color: {SURFACE};
        alternate-background-color: #171A1D;
        border: 1px solid {BORDER};
        border-radius: 7px;
        selection-background-color: #202D37;
        selection-color: {TEXT};
        outline: none;
    }}
    QTreeWidget#eventTree::item {{
        min-height: 36px; border-bottom: 1px solid #24272D;
    }}
    QTreeWidget#eventTree::item:hover {{ background-color: #1E252B; }}

    QDockWidget#eventInspectorDock {{
        background-color: {SURFACE}; border-left: 1px solid {BORDER};
    }}
    QFrame#inspectorTitleBar {{
        background-color: {SURFACE}; border-bottom: 1px solid {BORDER};
    }}
    QLabel#inspectorDockTitle {{
        color: {TEXT}; font-size: 13px; font-weight: 600;
    }}
    QPushButton#inspectorCloseButton {{
        color: #7D8591; background: transparent; border: none;
        font-size: 17px; padding: 0; min-height: 26px; max-width: 28px;
    }}
    QPushButton#inspectorCloseButton:hover {{ color: {TEXT}; }}
    QFrame#eventDetailFrame {{
        background-color: {SURFACE}; border: none;
    }}
    QLabel#eventDetailTitle {{
        color: {TEXT}; font-size: 15px; font-weight: 600;
    }}
    QLabel#inspectorCaption {{
        color: #727A86; font-size: 10px; font-weight: 600;
    }}
    QLabel#eventDetailSummary {{ color: #C4CBD1; font-size: 12px; }}
    QLabel#eventDetailMeta {{ color: #C7CDD5; font-size: 12px; }}
    QLabel#eventPathBlock {{
        color: #B9C2CE; background-color: #15171B;
        border: 1px solid {BORDER}; border-radius: 6px;
        padding: 8px;
        font-family: Menlo, Consolas, monospace;
        font-size: 11px;
    }}
    QLabel#eventDetailContext {{
        color: #9099A6; font-size: 11px;
        font-family: Menlo, Consolas, monospace;
    }}

    QDockWidget#sessionsDock {{
        background-color: #121416; border-right: 1px solid {BORDER};
    }}
    QFrame#sessionsTitleBar {{
        background-color: #121416;
        border: none;
        border-bottom: 1px solid {BORDER};
    }}
    QLabel#sessionsDockTitle {{
        color: #DDE2E7; font-size: 13px; font-weight: 500;
    }}
    QPushButton#sessionsCloseButton {{
        color: #727C85; background: transparent; border: none;
        font-size: 17px; padding: 0; min-height: 26px; max-width: 28px;
    }}
    QPushButton#sessionsCloseButton:hover {{ color: {TEXT}; }}
    QLabel#sessionsSummary, QLabel#reportPreview {{
        color: #AAB2B9;
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {BORDER};
        border-radius: 0;
        padding: 8px 2px;
        font-size: 11px;
        font-weight: 400;
    }}

    QListWidget {{
        color: #BFC6CC;
        background-color: {SURFACE};
        alternate-background-color: #171A1D;
        border: 1px solid {BORDER};
        border-radius: 7px;
        outline: none;
    }}
    QListWidget#sessionsList {{
        background-color: transparent;
        alternate-background-color: transparent;
        border: none;
    }}
    QListWidget#sessionsList::item {{
        color: #89939C;
        background-color: transparent;
        border: none;
        border-bottom: 1px solid #23282D;
        margin: 0;
        padding: 10px 5px;
    }}
    QListWidget#sessionsList::item:hover {{
        color: #D8DDE2; background-color: #181C1F;
    }}
    QListWidget#sessionsList::item:selected {{
        color: {TEXT}; background-color: #1A2025;
        border-left: 1px solid {ACCENT};
    }}

    QFrame#emptyState {{
        background-color: transparent; border: none; border-radius: 0;
    }}
    QLabel#emptyTitle {{
        color: #C8CED4; font-size: 15px; font-weight: 500;
    }}
    QLabel#emptyDescription {{ color: #77818A; font-size: 12px; }}
    QHeaderView::section {{
        color: #8E98A1;
        background-color: #171A1D;
        border: none;
        border-bottom: 1px solid #343A40;
        padding: 8px;
        font-size: 11px;
        font-weight: 500;
    }}
    QCheckBox {{ color: #B8C0C7; spacing: 8px; }}
    QScrollBar:vertical {{
        background: transparent; width: 8px; margin: 2px 2px 2px 0;
    }}
    QScrollBar::handle:vertical {{
        background: #3B4249; min-height: 28px; border-radius: 2px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{
        color: {TEXT}; background-color: #23272B;
        border: 1px solid #4A525A; padding: 5px;
    }}
"""
