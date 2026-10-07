from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from yula.gui.branding import filter_icon, search_icon, yula_icon
from yula.gui.delegates import RiskBadgeDelegate
from yula.gui.event_table import EventTreeWidget
from yula.gui.theme import APPLICATION_STYLESHEET


def build_main_window(window) -> None:
    """Ana pencerenin görünür bileşenlerini kurar."""
    self = window
    central_widget = QWidget()
    central_widget.setObjectName("centralWidget")
    self.setCentralWidget(central_widget)

    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(20, 12, 20, 10)
    main_layout.setSpacing(8)

    header_layout = QHBoxLayout()

    brand_mark = QLabel()
    brand_mark.setObjectName("brandMark")
    brand_mark.setPixmap(yula_icon().pixmap(34, 34))
    brand_mark.setFixedSize(38, 38)
    brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
    header_layout.addWidget(brand_mark)

    title_layout = QVBoxLayout()
    title_layout.setSpacing(2)

    title = QLabel("YULA")
    title.setObjectName("applicationTitle")

    self.target_summary = QLabel(
        "📁 Hedef seçilmedi · Durum: Seçim bekleniyor"
    )
    self.target_summary.setObjectName("headerBreadcrumb")
    self.target_summary.setMaximumWidth(680)
    self.target_summary.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )

    title_layout.addWidget(title)
    title_layout.addWidget(self.target_summary)

    header_layout.addLayout(title_layout)
    header_layout.addStretch()

    secondary_actions = QFrame()
    secondary_actions.setObjectName("secondaryActions")
    secondary_layout = QHBoxLayout(secondary_actions)
    secondary_layout.setContentsMargins(0, 0, 0, 0)
    secondary_layout.setSpacing(2)

    self.report_button = QPushButton("Rapor")
    self.report_button.setObjectName("reportButton")
    self.report_button.setToolTip("PDF güvenlik raporu oluştur")
    self.report_button.clicked.connect(self._open_report_dialog)
    secondary_layout.addWidget(self.report_button)

    self.sessions_button = QPushButton("Çalışmalar")
    self.sessions_button.setObjectName("sessionsButton")
    self.sessions_button.setCheckable(True)
    self.sessions_button.setChecked(False)
    self.sessions_button.setToolTip(
        "Geçmiş ve etkin izleme çalışmalarını aç"
    )
    self.sessions_button.clicked.connect(self._toggle_sessions_dock)
    secondary_layout.addWidget(self.sessions_button)
    header_layout.addWidget(secondary_actions)

    self.select_targets_button = QPushButton("+ Hedef Ekle")
    self.select_targets_button.setObjectName("primaryButton")
    self.select_targets_button.clicked.connect(
        self._open_target_selection
    )
    header_layout.addWidget(self.select_targets_button)

    self.stop_button = QPushButton("İzlemeyi Durdur")
    self.stop_button.setObjectName("dangerButton")
    self.stop_button.setEnabled(False)
    self.stop_button.clicked.connect(self._stop_monitoring)
    header_layout.addWidget(self.stop_button)

    main_layout.addLayout(header_layout)

    event_navigation = QFrame()
    event_navigation.setObjectName("unifiedToolbar")
    event_navigation_layout = QHBoxLayout(event_navigation)
    event_navigation_layout.setContentsMargins(8, 6, 8, 6)
    event_navigation_layout.setSpacing(7)

    self.event_view_tabs = QTabBar()
    self.event_view_tabs.setObjectName("eventViewTabs")
    self.event_view_tabs.setExpanding(False)
    self.event_view_tabs.addTab("Canlı Olay Akışı")
    self.event_view_tabs.addTab("Dosyaya Göre")

    event_navigation_layout.addWidget(self.event_view_tabs)
    self.session_label = QLabel("Aktif çalışma yok")
    self.session_label.setObjectName("sessionLabel")
    self.session_label.setMaximumWidth(320)
    event_navigation_layout.addWidget(self.session_label)
    event_navigation_layout.addStretch()

    self.search_input = QLineEdit()
    self.search_input.setPlaceholderText(
        "Dosya adı, yol veya açıklama ara"
    )
    self.search_input.setClearButtonEnabled(True)
    self.search_input.setMinimumWidth(180)
    self.search_input.setMaximumWidth(280)
    self.search_input.addAction(
        search_icon(),
        QLineEdit.ActionPosition.LeadingPosition,
    )
    self.search_input.textChanged.connect(
        self._refresh_events
    )

    self.event_filter_button = QToolButton()
    self.event_filter_button.setObjectName("eventFilterButton")
    self.event_filter_button.setIcon(filter_icon())
    self.event_filter_button.setIconSize(QSize(18, 18))
    self.event_filter_button.setToolTip("Olay türünü filtrele")
    self.event_filter_button.setAccessibleName("Olay türünü filtrele")
    self.event_filter_button.setPopupMode(
        QToolButton.ToolButtonPopupMode.InstantPopup
    )

    self.event_filter_menu = QMenu(self.event_filter_button)
    self.event_filter_group = QActionGroup(self.event_filter_menu)
    self.event_filter_group.setExclusive(True)
    self.event_filter_actions = {}
    filter_options = (
        ("ALL", "Tüm olaylar"),
        ("COPIES", "Kopyalamalar"),
        ("CHANGES", "Değişiklikler"),
        ("DELETIONS", "Silinenler"),
        ("AUTHORITY", "Yetki olayları"),
    )
    for category, label in filter_options:
        action = QAction(label, self.event_filter_menu)
        action.setCheckable(True)
        action.setChecked(category == "ALL")
        action.triggered.connect(
            lambda _checked=False, value=category: self._set_event_category(value)
        )
        self.event_filter_group.addAction(action)
        self.event_filter_menu.addAction(action)
        self.event_filter_actions[category] = action
    self.event_filter_button.setMenu(self.event_filter_menu)

    self.risk_filter = QComboBox()
    self.risk_filter.addItem(
        "Risk Düzeyi: Tümü",
        None,
    )
    self.risk_filter.addItem("Risk Düzeyi: Yüksek", "HIGH")
    self.risk_filter.addItem("Risk Düzeyi: Orta", "MEDIUM")
    self.risk_filter.addItem("Risk Düzeyi: Düşük", "LOW")
    self.risk_filter.currentIndexChanged.connect(
        self._refresh_events
    )

    self.live_follow_button = QToolButton()
    self.live_follow_button.setObjectName("liveFollowButton")
    self.live_follow_button.setText("● Canlı")
    self.live_follow_button.setCheckable(True)
    self.live_follow_button.setChecked(True)
    self.live_follow_button.setToolTip(
        "Açıkken yeni olay geldiğinde listenin en üstünü göster"
    )
    self.live_follow_button.toggled.connect(self._set_live_follow)

    self.refresh_button = QToolButton()
    self.refresh_button.setObjectName("refreshButton")
    self.refresh_button.setText("⟳")
    self.refresh_button.setToolTip("Olayları ve çalışmaları yenile")
    self.refresh_button.setAccessibleName("Yenile")
    self.refresh_button.clicked.connect(self._refresh_all)

    event_navigation_layout.addWidget(self.search_input)
    event_navigation_layout.addWidget(self.event_filter_button)
    event_navigation_layout.addWidget(self.risk_filter)
    event_navigation_layout.addWidget(self.live_follow_button)
    event_navigation_layout.addWidget(self.refresh_button)

    main_layout.addWidget(event_navigation)

    self.table = EventTreeWidget()
    self.table.setObjectName("eventTree")
    self.table.setColumnCount(6)
    self.table.setHeaderLabels([
        "Zaman",
        "Risk düzeyi",
        "Ne oldu?",
        "Dosya veya aktarım",
        "Olay ayrıntısı",
        "Kullanıcı bağlamı*",
    ])

    self.table.setEditTriggers(
        QAbstractItemView.EditTrigger.NoEditTriggers
    )
    self.table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    self.table.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection
    )
    self.table.setAlternatingRowColors(True)
    self.table.setRootIsDecorated(True)
    self.table.setItemsExpandable(True)
    self.table.setAnimated(True)
    self.table.setIndentation(22)
    self.table.setExpandsOnDoubleClick(True)
    self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
    self.table.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    self.table.itemClicked.connect(
        self._show_selected_event_details
    )
    self.table.itemDoubleClicked.connect(
        self._show_selected_event_details
    )
    self.table.userScrolledDown.connect(self._disable_live_follow)
    self.table.verticalScrollBar().sliderPressed.connect(
        self._disable_live_follow
    )
    self.table.verticalScrollBar().actionTriggered.connect(
        self._on_event_scroll_action
    )
    self.table.verticalScrollBar().valueChanged.connect(
        self._on_event_scroll_position_changed
    )
    self.risk_badge_delegate = RiskBadgeDelegate(self.table)
    self.table.setItemDelegateForColumn(1, self.risk_badge_delegate)

    header = self.table.header()

    header.setSectionResizeMode(
        0,
        QHeaderView.ResizeMode.Fixed,
    )
    header.setSectionResizeMode(
        1,
        QHeaderView.ResizeMode.Fixed,
    )
    header.setSectionResizeMode(
        2,
        QHeaderView.ResizeMode.Fixed,
    )
    header.setSectionResizeMode(
        3,
        QHeaderView.ResizeMode.Fixed,
    )
    header.setSectionResizeMode(
        4,
        QHeaderView.ResizeMode.Fixed,
    )
    header.setSectionResizeMode(
        5,
        QHeaderView.ResizeMode.Fixed,
    )
    header.setStretchLastSection(False)
    self.table.apply_column_widths()

    self.empty_state = QFrame()
    self.empty_state.setObjectName("emptyState")

    empty_layout = QVBoxLayout(self.empty_state)
    empty_layout.setContentsMargins(32, 48, 32, 48)
    empty_layout.setSpacing(8)
    empty_layout.addStretch()

    self.empty_title = QLabel(
        "İzleme başlatılmadı"
    )
    self.empty_title.setObjectName("emptyTitle")
    self.empty_title.setAlignment(
        Qt.AlignmentFlag.AlignCenter
    )

    self.empty_description = QLabel(
        "Dosya veya klasör seçerek başlayın."
    )
    self.empty_description.setObjectName(
        "emptyDescription"
    )
    self.empty_description.setAlignment(
        Qt.AlignmentFlag.AlignCenter
    )
    self.empty_description.setWordWrap(True)

    empty_layout.addWidget(self.empty_title)
    empty_layout.addWidget(
        self.empty_description
    )
    empty_layout.addStretch()

    self.event_stack = QStackedWidget()
    self.event_stack.addWidget(self.empty_state)
    self.event_stack.addWidget(self.table)

    main_layout.addWidget(self.event_stack, 1)

    self.event_view_tabs.currentChanged.connect(self._refresh_events)

    footer_layout = QHBoxLayout()

    self.event_count_label = QLabel(
        "0 olay görüntüleniyor"
    )
    self.event_count_label.setObjectName("footerLabel")

    footer_layout.addWidget(
        self.event_count_label
    )
    footer_layout.addStretch()

    main_layout.addLayout(footer_layout)

    self.setStyleSheet(APPLICATION_STYLESHEET)

    build_sessions_dock(self)
    build_event_inspector_dock(self)


def build_sessions_dock(window) -> None:
    """Geçmiş izleme çalışmalarının yan panelini kurar."""
    self = window
    self.sessions_dock = QDockWidget("Çalışmalar", self)
    self.sessions_dock.setObjectName("sessionsDock")
    self.sessions_dock.setAllowedAreas(
        Qt.DockWidgetArea.LeftDockWidgetArea
        | Qt.DockWidgetArea.RightDockWidgetArea
    )
    self.sessions_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    self.sessions_dock.setMinimumWidth(285)

    title_bar = QFrame()
    title_bar.setObjectName("sessionsTitleBar")
    title_layout = QHBoxLayout(title_bar)
    title_layout.setContentsMargins(14, 9, 8, 9)
    title_label = QLabel("İzleme Çalışmalarım")
    title_label.setObjectName("sessionsDockTitle")
    close_button = QPushButton("×")
    close_button.setObjectName("sessionsCloseButton")
    close_button.setToolTip("Çalışmalar panelini kapat")
    close_button.clicked.connect(self.sessions_dock.hide)
    title_layout.addWidget(title_label)
    title_layout.addStretch()
    title_layout.addWidget(close_button)
    self.sessions_dock.setTitleBarWidget(title_bar)

    dock_content = QFrame()
    dock_layout = QVBoxLayout(dock_content)
    dock_layout.setContentsMargins(12, 14, 12, 12)
    dock_layout.setSpacing(9)

    status_layout = QHBoxLayout()
    status_layout.setSpacing(8)
    self.status_dot = QLabel()
    self.status_dot.setObjectName("statusDot")
    self.status_dot.setFixedSize(7, 7)
    self.sidebar_status_label = QLabel("SEÇİM BEKLENİYOR")
    self.sidebar_status_label.setObjectName("sidebarStatusLabel")
    status_layout.addWidget(self.status_dot)
    status_layout.addWidget(self.sidebar_status_label)
    status_layout.addStretch()

    explanation = QLabel(
        "Geçmiş veya etkin bir çalışmayı seçerek olaylarını ayrı inceleyin."
    )
    explanation.setWordWrap(True)
    explanation.setObjectName("sectionDescription")

    self.sessions_summary = QLabel("Henüz çalışma yok")
    self.sessions_summary.setObjectName("sessionsSummary")

    self.sessions_list = QListWidget()
    self.sessions_list.setObjectName("sessionsList")
    self.sessions_list.setAlternatingRowColors(True)
    self.sessions_list.setIconSize(QSize(14, 14))
    self.sessions_list.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection
    )
    self.sessions_list.currentItemChanged.connect(
        self._on_session_selected
    )

    dock_layout.addLayout(status_layout)
    dock_layout.addWidget(explanation)
    dock_layout.addWidget(self.sessions_summary)
    dock_layout.addWidget(self.sessions_list, 1)

    refresh_sessions_button = QPushButton("Çalışma listesini yenile")
    refresh_sessions_button.clicked.connect(
        lambda: self._refresh_sessions(
            select_session_id=self.current_session_id
        )
    )
    dock_layout.addWidget(refresh_sessions_button)
    self.sessions_dock.setWidget(dock_content)
    self.addDockWidget(
        Qt.DockWidgetArea.LeftDockWidgetArea,
        self.sessions_dock,
    )
    self.sessions_dock.visibilityChanged.connect(
        self._update_sessions_button_state
    )
    self.sessions_dock.hide()


def build_event_inspector_dock(window) -> None:
    """Seçilen olayın ayrıntılarını sağdaki isteğe bağlı panelde gösterir."""
    self = window
    self.event_inspector_dock = QDockWidget("Olay Ayrıntısı", self)
    self.event_inspector_dock.setObjectName("eventInspectorDock")
    self.event_inspector_dock.setAllowedAreas(
        Qt.DockWidgetArea.RightDockWidgetArea
    )
    self.event_inspector_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    self.event_inspector_dock.setMinimumWidth(320)
    self.event_inspector_dock.setMaximumWidth(420)

    title_bar = QFrame()
    title_bar.setObjectName("inspectorTitleBar")
    title_layout = QHBoxLayout(title_bar)
    title_layout.setContentsMargins(16, 10, 8, 10)
    title_label = QLabel("Olay Ayrıntısı")
    title_label.setObjectName("inspectorDockTitle")
    close_button = QPushButton("×")
    close_button.setObjectName("inspectorCloseButton")
    close_button.setToolTip("Ayrıntı panelini kapat")
    close_button.clicked.connect(self.event_inspector_dock.hide)
    title_layout.addWidget(title_label)
    title_layout.addStretch()
    title_layout.addWidget(close_button)
    self.event_inspector_dock.setTitleBarWidget(title_bar)

    self.event_detail_frame = QFrame()
    self.event_detail_frame.setObjectName("eventDetailFrame")
    detail_layout = QVBoxLayout(self.event_detail_frame)
    detail_layout.setContentsMargins(18, 18, 18, 18)
    detail_layout.setSpacing(12)

    inspector_heading = QHBoxLayout()
    inspector_heading.setSpacing(10)
    self.event_detail_title = QLabel("Bir olay seçin")
    self.event_detail_title.setObjectName("eventDetailTitle")
    self.event_detail_title.setWordWrap(True)

    self.event_detail_risk = QLabel()
    self.event_detail_risk.setObjectName("eventDetailRisk")
    self.event_detail_risk.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.event_detail_risk.setMaximumWidth(110)
    inspector_heading.addWidget(self.event_detail_title, 1)
    inspector_heading.addWidget(self.event_detail_risk)

    summary_caption = QLabel("OLAY ÖZETİ")
    summary_caption.setObjectName("inspectorCaption")
    self.event_detail_summary = QLabel()
    self.event_detail_summary.setObjectName("eventDetailSummary")
    self.event_detail_summary.setWordWrap(True)
    self.event_detail_summary.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )

    time_caption = QLabel("ZAMAN")
    time_caption.setObjectName("inspectorCaption")
    self.event_detail_time = QLabel()
    self.event_detail_time.setObjectName("eventDetailMeta")

    path_caption = QLabel("TAM DOSYA YOLU")
    path_caption.setObjectName("inspectorCaption")
    self.event_detail_path = QLabel()
    self.event_detail_path.setObjectName("eventPathBlock")
    self.event_detail_path.setWordWrap(True)
    self.event_detail_path.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )

    change_caption = QLabel("DEĞİŞİKLİK TÜRÜ")
    change_caption.setObjectName("inspectorCaption")
    self.event_detail_change = QLabel()
    self.event_detail_change.setObjectName("eventDetailMeta")

    hash_caption = QLabel("SHA-256 ÖZETİ")
    hash_caption.setObjectName("inspectorCaption")
    self.event_detail_hash = QLabel()
    self.event_detail_hash.setObjectName("eventPathBlock")
    self.event_detail_hash.setWordWrap(True)
    self.event_detail_hash.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )

    context_caption = QLabel("KULLANICI / SÜREÇ")
    context_caption.setObjectName("inspectorCaption")
    self.event_detail_context = QLabel()
    self.event_detail_context.setObjectName("eventDetailContext")
    self.event_detail_context.setWordWrap(True)
    self.event_detail_context.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )

    detail_layout.addLayout(inspector_heading)
    detail_layout.addSpacing(6)
    detail_layout.addWidget(summary_caption)
    detail_layout.addWidget(self.event_detail_summary)
    detail_layout.addSpacing(10)
    detail_layout.addWidget(time_caption)
    detail_layout.addWidget(self.event_detail_time)
    detail_layout.addWidget(path_caption)
    detail_layout.addWidget(self.event_detail_path)
    detail_layout.addWidget(change_caption)
    detail_layout.addWidget(self.event_detail_change)
    detail_layout.addWidget(hash_caption)
    detail_layout.addWidget(self.event_detail_hash)
    detail_layout.addWidget(context_caption)
    detail_layout.addWidget(self.event_detail_context)
    detail_layout.addStretch()

    self.event_inspector_dock.setWidget(self.event_detail_frame)
    self.addDockWidget(
        Qt.DockWidgetArea.RightDockWidgetArea,
        self.event_inspector_dock,
    )
    self.event_inspector_dock.hide()
