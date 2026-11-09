from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(r"C:\Users\warti\Documents\Codex\2026-11-03\new-chat")
REPO = ROOT / "wireless-link-failover"
REFERENCE = Path(r"C:\AI\models\qwen38\EMCS_article.docx")
ASSETS = REPO / "article" / "assets"
OUTPUT = Path(os.environ.get("WLF_ARTICLE_RU_OUTPUT", REPO / "article" / "Wireless_Link_Failover_article_ru.docx"))
OUTPUT_DIR = OUTPUT.parent
EXPECTED_REFERENCE_HASH = "DD82CE1DB944CDAE0F9A4B386EBDC08375FD90EA662130CB2F2D355C1D2DF07C"


def set_run_font(run, size=None, bold=None, italic=None, color="000000", name="Times New Roman"):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    run.font.color.rgb = RGBColor.from_string(color)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=90, start=100, bottom=90, end=100):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table, color="B7B7B7", size="6"):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:color"), color)


def prevent_row_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_repeat_table_layout(table, widths):
    table.autofit = False
    for row in table.rows:
        prevent_row_split(row)
        for index, cell in enumerate(row.cells):
            cell.width = widths[index]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)


def remove_document_body(doc):
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def ensure_black_styles(doc):
    for style_name in ("Article Title", "Title", "Heading 1", "Heading 2", "Caption", "Normal"):
        if style_name not in doc.styles:
            continue
        style = doc.styles[style_name]
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.name = "Times New Roman"
        style._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Times New Roman")
        style._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Times New Roman")
        style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal = doc.styles["Normal"]
    normal.font.size = Pt(11)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.first_line_indent = Cm(1.25)
    normal.paragraph_format.space_after = Pt(2.5)
    normal.paragraph_format.line_spacing = 1.05


def add_body(doc, text, *, first_indent=True, keep_with_next=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    paragraph = doc.add_paragraph(style="Normal")
    paragraph.alignment = align
    paragraph.paragraph_format.first_line_indent = Cm(1.25) if first_indent else Cm(0)
    paragraph.paragraph_format.keep_with_next = keep_with_next
    run = paragraph.add_run(text)
    set_run_font(run, 11)
    return paragraph


def add_labeled_paragraph(doc, label, text):
    paragraph = doc.add_paragraph(style="Normal")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.first_line_indent = Cm(1.25)
    run = paragraph.add_run(label)
    set_run_font(run, 11, bold=True)
    run = paragraph.add_run(text)
    set_run_font(run, 11)
    return paragraph


def add_heading(doc, text, level=1):
    paragraph = doc.add_paragraph(style=f"Heading {level}")
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.first_line_indent = Cm(0)
    run = paragraph.add_run(text)
    set_run_font(run, 12 if level == 1 else 11, bold=True)
    return paragraph


def add_figure(doc, filename, width, ru_caption, en_caption):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    picture = paragraph.add_run().add_picture(str(ASSETS / filename), width=Inches(width))
    # Store meaningful alternative text in the inline drawing metadata so the
    # scientific figures remain understandable to assistive technologies.
    picture._inline.docPr.set("title", filename)
    picture._inline.docPr.set("descr", ru_caption)
    caption = doc.add_paragraph(style="Caption")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.first_line_indent = Cm(0)
    caption.paragraph_format.keep_together = True
    caption.paragraph_format.keep_with_next = False
    run = caption.add_run(ru_caption)
    set_run_font(run, 9, bold=True)
    run = caption.add_run("\n" + en_caption)
    set_run_font(run, 9, bold=True, italic=True)
    return caption


def add_table(doc, number, ru_title, en_title, headers, rows, widths, aligns=None, font_size=9.5):
    caption = doc.add_paragraph(style="Normal")
    caption.alignment = WD_ALIGN_PARAGRAPH.LEFT
    caption.paragraph_format.first_line_indent = Cm(0)
    caption.paragraph_format.space_before = Pt(4)
    caption.paragraph_format.space_after = Pt(2)
    caption.paragraph_format.keep_with_next = True
    run = caption.add_run(f"Таблица {number} - {ru_title} / Table {number} - {en_title}")
    set_run_font(run, 10, bold=True)
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_repeat_table_layout(table, [Inches(value) for value in widths])
    set_table_borders(table)
    repeat_header(table.rows[0])
    for column, header in enumerate(headers):
        cell = table.rows[0].cells[column]
        set_cell_shading(cell, "F2F2F2")
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(header)
        set_run_font(run, font_size, bold=True)
    for row_index, values in enumerate(rows, 1):
        cells = table.add_row().cells
        prevent_row_split(table.rows[-1])
        for column, value in enumerate(values):
            cell = cells[column]
            cell.width = Inches(widths[column])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            set_cell_shading(cell, "FFFFFF")
            paragraph = cell.paragraphs[0]
            paragraph.alignment = (aligns[column] if aligns else WD_ALIGN_PARAGRAPH.LEFT)
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            run = paragraph.add_run(str(value))
            set_run_font(run, font_size)
    set_repeat_table_layout(table, [Inches(value) for value in widths])
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(1)
    spacer.paragraph_format.first_line_indent = Cm(0)
    return table


def add_reference(doc, number, text):
    paragraph = doc.add_paragraph(style="Normal")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.left_indent = Cm(0.5)
    paragraph.paragraph_format.first_line_indent = Cm(-0.5)
    paragraph.paragraph_format.space_after = Pt(1.5)
    paragraph.paragraph_format.line_spacing = 1.0
    run = paragraph.add_run(f"{number}. {text}")
    set_run_font(run, 9)


def build():
    current_hash = hashlib.sha256(REFERENCE.read_bytes()).hexdigest().upper()
    if current_hash != EXPECTED_REFERENCE_HASH:
        raise RuntimeError(f"Reference hash changed: {current_hash}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REFERENCE, OUTPUT)
    doc = Document(OUTPUT)
    remove_document_body(doc)
    ensure_black_styles(doc)
    doc.core_properties.title = "Исследование межпоколенческой совместимости ESP-NOW и резервного перехода на UDP"
    doc.core_properties.subject = "ESP8266, ESP32, ESP32-S3, ESP-NOW, UDP, автоматический failover"
    doc.core_properties.author = "Бембиев Ф.Э.; Кадеров В.А."
    doc.core_properties.keywords = "ESP-NOW, UDP, ESP8266, ESP32, ESP32-S3, failover, совместимость"

    title = doc.add_paragraph(style="Article Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.keep_with_next = True
    run = title.add_run("Исследование межпоколенческой совместимости ESP-NOW и автоматического резервного перехода на UDP в гетерогенной сети ESP8266, ESP32 и ESP32-S3")
    set_run_font(run, 15, bold=True)

    authors = doc.add_paragraph(style="Normal")
    authors.alignment = WD_ALIGN_PARAGRAPH.CENTER
    authors.paragraph_format.first_line_indent = Cm(0)
    authors.paragraph_format.space_after = Pt(2)
    run = authors.add_run("АВТОР 1: Бембиев Ф.Э.     АВТОР 2: Кадеров В.А.")
    set_run_font(run, 11, bold=True)
    affiliation = doc.add_paragraph(style="Normal")
    affiliation.alignment = WD_ALIGN_PARAGRAPH.CENTER
    affiliation.paragraph_format.first_line_indent = Cm(0)
    affiliation.paragraph_format.space_after = Pt(8)
    run = affiliation.add_run("МАИ (НИУ), Москва, Россия")
    set_run_font(run, 11)

    abstract = (
        "В работе исследована межпоколенческая совместимость ESP-NOW и разработан автоматический механизм резервного переключения на Wi-Fi/UDP для узлов ESP8266, ESP32 и ESP32-S3. Все платформы используют единый 20-байтовый пакет с номером последовательности, временем работы и CRC32, а факт доставки подтверждается прикладным ACK. Основным транспортом служит ESP-NOW, резервным - UDP через точку доступа; выбор выполняется оконным автоматом с гистерезисом. Испытания проведены для всех трёх аппаратных пар на расстоянии около 1 м, в сети 2,4 ГГц на канале 6, при отключённом энергосбережении Wi-Fi. Для каждой пары выполнено по пять управляемых циклов, в которых подавлялись только прикладные ESP-NOW ACK. Переход на UDP и возврат на ESP-NOW состоялись во всех 15 циклах. До отказа получено 843 из 843 ACK. Среднее время перехода составило 8,613 с, среднее время возврата - 15,707 с. Резервный UDP доставил 323 из 374 ACK (86,364 %), при этом для пары ESP32-ESP32-S3 показатель снизился до 68,519 %. Результаты подтверждают работоспособность общего автомата на трёх поколениях микроконтроллеров, но показывают, что успешное переключение не эквивалентно гарантированной доставке UDP и требует отдельного механизма повторов."
    )
    add_body(doc, abstract, first_indent=False)
    keywords = doc.add_paragraph(style="Normal")
    keywords.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    keywords.paragraph_format.first_line_indent = Cm(0)
    keywords.paragraph_format.space_after = Pt(8)
    run = keywords.add_run("Ключевые слова: ")
    set_run_font(run, 10, bold=True)
    run = keywords.add_run("ESP-NOW, UDP, ESP8266, ESP32, ESP32-S3, отказоустойчивость, резервирование транспорта, Интернет вещей, встроенные системы.")
    set_run_font(run, 10)

    add_heading(doc, "1 Введение", 1)
    add_body(doc, "Беспроводные микроконтроллерные узлы применяются в распределённых датчиках, системах управления, учебных стендах и устройствах Интернета вещей. Для таких систем важны малая задержка, низкая стоимость и возможность продолжить обмен при ухудшении основной линии. Семейства ESP8266 и ESP32 удобны тем, что объединяют микроконтроллер и радиотракт 2,4 ГГц, однако реальные проекты нередко включают платы разных поколений, выпущенные в разные годы и использующие разные версии программных стеков.")
    add_body(doc, "ESP-NOW позволяет передавать короткие кадры непосредственно между устройствами без обязательного участия точки доступа. Протокол использует радиоблок Wi-Fi и подходит для локального обмена с малой служебной нагрузкой. Документация Espressif указывает, что библиотека Arduino-ESP32 тестируется на семействе ESP32, а совместимость с ESP8266 не гарантируется [1]. Одновременно API требует согласования радиоканала: нулевое значение канала peer означает использование текущего канала станции или точки доступа [2]. Поэтому работоспособность смешанной пары нельзя считать следствием одного совпадения названий функций; её необходимо подтверждать аппаратным экспериментом.")
    add_body(doc, "Опубликованные работы в основном оценивают дальность, задержку, джиттер, энергопотребление и потери ESP-NOW. В полевых исследованиях показано ухудшение доставки с увеличением расстояния и изменением среды [4, 5], а сравнительные эксперименты отмечают преимущества ESP-NOW по задержке и энергопотреблению относительно некоторых конфигураций Wi-Fi и Bluetooth [6]. Отдельно исследованы многопользовательские и шлюзовые сценарии [7, 8]. Эти результаты важны для выбора транспорта, однако не отвечают на вопрос, может ли единый программный автомат одинаково переключать три поколения узлов между прямой связью ESP-NOW и инфраструктурным UDP.")
    add_body(doc, "UDP выбран в качестве резерва из-за доступности во всех трёх программных средах и возможности сохранить тот же формат прикладного пакета. При этом сам UDP не обеспечивает повторную передачу, порядок и подавление дубликатов [9, 10]. Следовательно, резервный тракт нужно оценивать отдельно: переход состояния может завершиться корректно даже при неполной доставке прикладных подтверждений. Такое разделение особенно важно для инженерной статьи, поскольку иначе успешное изменение выбранного транспорта можно ошибочно принять за доказательство надёжности всей линии.")
    add_body(doc, "Цель работы - разработать и экспериментально проверить единый механизм автоматического перехода ESP-NOW - UDP - ESP-NOW для ESP8266, ESP32 и ESP32-S3. Проверялась гипотеза о том, что одинаковые формат пакета, оконные критерии и разнесение радиослотов позволят воспроизводимо выполнить переход и возврат на всех трёх аппаратных парах. Для достижения цели реализованы прикладные ACK, контроль CRC и sequence, автомат с гистерезисом, настольный интерфейс управления и воспроизводимая процедура управляемого отказа.")
    add_body(doc, "Экспериментальная матрица содержит 15 циклов для трёх аппаратных пар. Для каждого цикла зарегистрированы времена перехода и восстановления, доставка резервного UDP и финальные окна ESP-NOW. Один формат пакета, один автомат и одна схема телеметрии применялись к ESP8266, ESP32 и ESP32-S3. Выводы относятся к контролируемому стенду; дальность, помехи, полный отказ питания и одновременная работа трёх отправителей в эту серию не входили.")

    add_heading(doc, "2 Материалы и методы", 1)
    add_heading(doc, "2.1 Аппаратные и программные средства", 2)
    add_body(doc, "Стенд построен на трёх имеющихся отладочных платах. Узел ESP8266 использует модуль ESP-12E, классический ESP32 - модуль ESP32-D0WD-V3, а узел нового поколения - ESP32-S3-N16R8. Прошивки собирались в VS Code с PlatformIO. Для ESP8266 применялись Espressif 8266 Platform 4.2.1 и Arduino Core 3.1.2; для ESP32 и ESP32-S3 - Espressif 32 Platform 8.0.0, Arduino Core 3.3.12 и ESP-IDF 5.5.5. Управляющее приложение и анализ журналов реализованы на Python 3.11.")
    add_figure(doc, "hardware_nodes.png", 6.25, "Рис. 1. Аппаратные узлы экспериментального стенда", "Fig. 1. Hardware nodes used in the experiment")
    add_table(
        doc, 1, "Состав экспериментального стенда", "Experimental testbed components",
        ["Компонент", "Исполнение", "Назначение"],
        [
            ["ESP8266", "NodeMCU 1.0, ESP-12E, 80 МГц, 4 Мбайт flash", "Межпоколенческий узел 1"],
            ["ESP32", "38-pin DevKit, ESP32-D0WD-V3, 2 ядра, 240 МГц", "Межпоколенческий узел 2"],
            ["ESP32-S3", "DevKitC-совместимая, N16R8, 2 ядра, 240 МГц", "Межпоколенческий узел 3"],
            ["Маршрутизатор", "Huawei WiFi AX1 / WS5203", "UDP, сеть 2,4 ГГц, канал 6"],
            ["Компьютер", "Windows, VS Code, PlatformIO, Python 3.11", "Прошивка, GUI, сбор JSONL"],
        ],
        [1.05, 2.75, 2.62],
        [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT],
        9.2,
    )
    add_body(doc, "Во время зачётных серий платы находились примерно в 100 см друг от друга на неметаллической поверхности. Оба активных узла подключались к лабораторной сети Lab-2G в диапазоне 2,4 ГГц; телеметрия фиксировала канал 6. Энергосбережение Wi-Fi принудительно отключалось. Это увеличивает потребление, но уменьшает задержку приёма и устраняет зависимость от DTIM; документация Espressif рекомендует WIFI_PS_NONE для минимальной задержки приёма в реальном времени [11].")

    add_heading(doc, "2.2 Архитектура обмена", 2)
    add_body(doc, "В каждом опыте работала одна аппаратная пара, а третья плата не участвовала в обмене. Активный отправитель формировал probe, пассивный приёмник проверял пакет и возвращал прикладной ACK. ESP-NOW использовался как основной прямой транспорт. UDP заранее запускался на том же узле и проходил через маршрутизатор: probe передавался широковещательно в локальной подсети, ACK возвращался одноадресно на IP отправителя. Компьютер подавал команды по USB Serial и записывал все события обеих плат в единый журнал JSON Lines.")
    add_figure(doc, "architecture_ru.png", 6.25, "Рис. 2. Архитектура экспериментального стенда", "Fig. 2. Architecture of the experimental testbed")
    add_body(doc, "Совместная работа ESP-NOW и инфраструктурного Wi-Fi требует общего радиоканала. После подключения к точке доступа прошивка считывала текущий канал и повторно регистрировала широковещательный peer ESP-NOW с каналом 0, то есть с использованием канала интерфейса станции [2]. Такой подход исключал скрытое различие каналов как причину отсутствия связи и позволял переключать прикладной транспорт без перенастройки радиотракта.")

    add_heading(doc, "2.3 Формат пакета и прикладные подтверждения", 2)
    add_body(doc, "Оба транспорта используют одну packed-структуру размером 20 байт с порядком little-endian. Получатель проверяет длину, сигнатуру, версию и CRC32. Callback радиодрайвера только копирует событие в статическую очередь, а формирование JSON и печать выполняются в основном цикле. Это уменьшает длительность обработчика Wi-Fi и делает телеметрию сопоставимой на платформах с разным объёмом памяти.")
    add_table(
        doc, 2, "Формат экспериментального пакета", "Experimental packet format",
        ["Смещение", "Размер", "Поле", "Назначение"],
        [
            ["0", "4", "magic", "Сигнатура WLF1"],
            ["4", "1", "version", "Версия формата, значение 1"],
            ["5", "1", "messageType", "1 - probe; 2 - ACK"],
            ["6", "1", "senderNode", "1 - ESP8266; 2 - ESP32; 3 - ESP32-S3"],
            ["7", "1", "flags", "Адресат прикладного ACK"],
            ["8", "4", "sequence", "Возрастающий номер передачи"],
            ["12", "4", "senderUptimeMs", "Время millis() отправителя"],
            ["16", "4", "crc32", "CRC32 байтов 0-15, полином 0xEDB88320"],
        ],
        [0.7, 0.62, 1.25, 3.85],
        [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT],
        8.9,
    )
    add_body(doc, "Результат отправки broadcast-кадра локальным драйвером не использовался как доказательство удалённого приёма. Для этого формировался пакет ACK типа 2, повторяющий sequence подтверждаемого probe. Отправитель сопоставлял ACK с кольцевой таблицей последних сообщений и вычислял RTT. Те же поля и правила проверки применялись к UDP, что позволяло сравнивать транспорты на одном прикладном уровне.")

    add_heading(doc, "2.4 Автомат выбора транспорта", 2)
    add_body(doc, "Автомат оценивает долю прикладных ACK в неперекрывающихся окнах. После запуска три окна используются для стабилизации и не вызывают переключения. В основном состоянии probe ESP-NOW отправляется каждые 470 мс. Если потери не менее 30 % наблюдаются в двух последовательных окнах по 5000 мс, выбирается UDP. Во время резерва сохраняются контрольные probe ESP-NOW, по которым оценивается восстановление. Возврат происходит после трёх окон с успешностью не менее 80 %.")
    add_figure(doc, "state_machine_ru.png", 6.25, "Рис. 3. Автомат выбора транспорта", "Fig. 3. Transport selection state machine")
    add_table(
        doc, 3, "Параметры стандартизированного автомата", "Standardized state-machine parameters",
        ["Параметр", "Значение", "Назначение"],
        [
            ["Период основного probe", "470 мс", "Частота оценки ESP-NOW"],
            ["Окно оценки", "5000 мс", "Неперекрывающийся интервал статистики"],
            ["Порог перехода", "потери ≥ 30 %", "Квалификация плохого окна"],
            ["Плохих окон", "2", "Гистерезис перед UDP"],
            ["Recovery probe", "940 мс", "Контроль ESP-NOW в состоянии UDP"],
            ["Сдвиг / guard", "235 / 470 мс", "Разнесение передач общего радиоблока"],
            ["Порог возврата", "ACK ≥ 80 %", "Квалификация хорошего окна"],
            ["Хороших окон", "3", "Гистерезис перед возвратом"],
        ],
        [2.35, 1.25, 2.82],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT],
        9.0,
    )
    add_body(doc, "UDP и ESP-NOW используют один радиоблок. В ранних диагностических опытах независимые таймеры могли ставить обе передачи в один цикл и ухудшать восстановительные ACK. Поэтому recovery probe сдвинут на 235 мс и дополнительно защищён интервалом 470 мс; в резервном режиме фактически чередуются отдельные слоты UDP и ESP-NOW. Если инфраструктурный Wi-Fi становится недоступен, прошивка возвращается к ESP-NOW, поскольку продолжение UDP без точки доступа невозможно.")

    add_heading(doc, "2.5 Управление и регистрация данных", 2)
    add_body(doc, "Настольное приложение обнаруживает последовательные порты, позволяет выбрать отправителя и приёмник, подключает узлы к Wi-Fi, задаёт конфигурацию автомата и управляет подавлением ACK. Кнопка создания отказа блокируется до окончания подготовительного интервала. События radio_info, wifi_status, failover_window, failover_transition, fault_control и udp_info сохраняются с временными метками хоста. Пароль сети передаётся только в оперативную память устройств и не попадает в журнал.")
    add_figure(doc, "console.png", 6.25, "Рис. 4. Интерфейс управления и регистрации эксперимента", "Fig. 4. Experiment control and logging interface")
    add_body(doc, "Для каждого зачётного повтора анализатор выделяет один законченный цикл от failover_enabled до возврата на ESP-NOW, проверяет последовательность событий и рассчитывает baseline, время от ACK OFF до перехода, время от ACK ON до возврата, доставку UDP и итоговые окна восстановления. Каждый агрегированный JSON содержит путь и SHA-256 стабильного снимка исходного журнала. Это связывает итоговые числа с неизменяемыми первичными данными, даже если большой JSONL не публикуется в Git.")

    add_heading(doc, "2.6 Экспериментальный протокол", 2)
    add_body(doc, "Для каждой из трёх аппаратных пар выполнено пять контролируемых циклов. Один узел назначался активным отправителем, второй - пассивным приёмником. После подключения к точке доступа выполнялись сброс статистики, включение автомата и подготовка базовой линии. Затем на приёмнике командой ESPNOW ACK OFF подавлялись только прикладные подтверждения ESP-NOW. Радиоинтерфейс, питание, Wi-Fi и UDP оставались работоспособными, поэтому опыт моделирует логическую деградацию основного транспорта, а не полный отказ узла.")
    add_figure(doc, "timeline_ru.png", 6.25, "Рис. 5. Стандартизированный цикл управляемого отказа", "Fig. 5. Standardized controlled-failure cycle")
    add_body(doc, "После автоматического перехода на UDP фиксировалась работа резерва. Затем командой ESPNOW ACK ON прикладные подтверждения восстанавливались, а автомат должен был накопить три хороших окна и самостоятельно вернуться к ESP-NOW. Для пары ESP32-ESP32-S3 GUI выдерживал 30-секундный guard; по меткам платы подготовка составила 29,691-48,943 с с допустимой погрешностью временных шкал 1 с и не менее чем пятью завершёнными окнами. В серии ESP8266-ESP32-S3 отказ включался раньше, через 16,284-26,429 с, но во всех повторах до него завершились три стабилизационных окна со 100 % ACK. Это отклонение сохранено в данных и учитывается при интерпретации.")

    add_heading(doc, "2.7 Метрики и статистическая обработка", 2)
    add_body(doc, "Основными метриками служили: доля ACK до отказа; факт перехода и возврата; время реакции после создания и снятия отказа; доля ACK резервного UDP; доля ACK в финальных окнах восстановления; время нахождения в UDP. Для времён рассчитывались минимум, среднее, медиана, максимум и выборочное стандартное отклонение. Пять повторов на пару достаточны для демонстрации воспроизводимости алгоритма, но не для строгого вывода о превосходстве одной аппаратной платформы или направленной асимметрии. Поэтому результаты представлены описательно, без проверки статистических гипотез.")

    add_heading(doc, "3 Результаты", 1)
    add_heading(doc, "3.1 Предварительная совместимость ESP-NOW", 2)
    add_body(doc, "До проверки автомата выполнены двусторонние серии ESP-NOW с прикладными подтверждениями. Для пары ESP32-ESP32-S3 получено 1000/1000 ACK в каждом направлении. В двух сериях по 1000 пакетов для ESP32-ESP8266 полный успех составил 1998/2000 и 1988/2000 в противоположных направлениях. Для ESP8266-ESP32-S3 в исходном близком размещении получено 1999/2000 и 1952/2000 ACK. Таким образом, обмен всех поколений практически осуществим, хотя доля доставки зависит от направления и условий. Этот вывод не отменяет официального предупреждения о негарантированной совместимости ESP8266 [1].")
    add_body(doc, "Отдельный опыт подтвердил работу ESP-NOW при одновременном подключении узлов к точке доступа и переводе на канал 6. Это необходимое условие резервирования: если основной транспорт работал бы на другом канале, переход на UDP требовал бы перестройки радио и создавал дополнительный неконтролируемый интервал. В зачётных циклах базовая линия была устойчивой во всех парах.")

    add_heading(doc, "3.2 Итоговая матрица переключений", 2)
    add_table(
        doc, 4, "Результаты по аппаратным парам", "Results for each hardware pair",
        ["Пара", "Переход / возврат", "ESP-NOW до отказа", "Переход, с", "Возврат, с", "UDP ACK"],
        [
            ["ESP8266-ESP32", "5/5", "308/308", "7,689", "15,214", "120/133 (90,226 %)"],
            ["ESP8266-ESP32-S3", "5/5", "193/193", "8,284", "15,229", "129/133 (96,992 %)"],
            ["ESP32-ESP32-S3", "5/5", "342/342", "9,867", "16,678", "74/108 (68,519 %)"],
        ],
        [1.35, 1.0, 1.0, 0.85, 0.85, 1.37],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER],
        8.4,
    )
    add_body(doc, "Во всех 15 опытах автомат обнаружил ухудшение, выбрал UDP и после снятия отказа вернулся на ESP-NOW. До отказа получено 843/843 ACK. Среднее время перехода по всем циклам составило 8,613 с при медиане 8,405 с, диапазоне 6,678-11,500 с и выборочном стандартном отклонении 1,575 с. Среднее время возврата составило 15,707 с при медиане 14,851 с, диапазоне 13,848-18,392 с и стандартном отклонении 1,732 с.")
    add_figure(doc, "results_ru.png", 6.35, "Рис. 6. Времена переключения и доставка прикладных ACK для трёх аппаратных пар", "Fig. 6. Switching times and application ACK delivery for the three hardware pairs")
    add_body(doc, "Наблюдаемые времена согласуются с логикой автомата. Два плохих окна по 5 с задают номинальное время обнаружения порядка 10 с; расхождение связано с фазой начала окна относительно команды ACK OFF. Три хороших окна задают минимальное время восстановления около 15 с. Один более длинный интервал UDP в серии ESP8266-ESP32-S3 составил 40,036 с, однако все возвраты завершились без ручного выбора транспорта.")

    add_heading(doc, "3.3 Доставка резервного UDP", 2)
    add_body(doc, "По совокупности опытов UDP доставил 323 из 374 наблюдаемых прикладных ACK, или 86,364 %. Между парами выявлена заметная неоднородность: 90,226 % для ESP8266-ESP32, 96,992 % для ESP8266-ESP32-S3 и 68,519 % для ESP32-ESP32-S3. Особенно важно, что низкое значение третьей пары не остановило восстановление: после включения ACK в её финальных окнах ESP-NOW получено 79/80 подтверждений, а по всей матрице - 232/240 (96,667 %).")
    add_body(doc, "Критерий завершения опыта разделяет исправность автомата и качество полезного трафика. Автомат считается сработавшим при зарегистрированных переходе и возврате, а резервный транспорт оценивается по собственным ACK. Результат 74/108 для ESP32-ESP32-S3 исключает трактовку прототипа как канала с гарантированной доставкой. Резервный путь сохраняет обмен, но отдельные датаграммы могут быть потеряны.")

    add_heading(doc, "3.4 Направления ESP32 и ESP32-S3", 2)
    add_table(
        doc, 5, "Направления в серии ESP32-ESP32-S3", "Directions in the ESP32-ESP32-S3 series",
        ["Отправитель", "Повторов", "Переход, с", "Возврат, с", "UDP ACK"],
        [
            ["ESP32 → ESP32-S3", "3", "9,562", "17,027", "45/71 (63,380 %)"],
            ["ESP32-S3 → ESP32", "2", "10,324", "16,154", "29/37 (78,378 %)"],
        ],
        [1.85, 0.85, 1.15, 1.15, 1.42],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER],
        9.0,
    )
    add_body(doc, "Различие UDP между направлениями составляет около 15 процентных пунктов, но основано на трёх и двух повторах и разном числе наблюдаемых пакетов. Поэтому оно рассматривается как основание для следующего эксперимента, а не как доказанная аппаратная асимметрия. Для отдельного статистического вывода необходимо не менее пяти повторов каждого направления с рандомизированным порядком и контролем загрузки точки доступа.")

    add_heading(doc, "4 Обсуждение", 1)
    add_body(doc, "Один алгоритм выполнил переход и возврат на всех трёх попарных сочетаниях ESP8266, ESP32 и ESP32-S3. Официальная документация не гарантирует совместимость ESP8266 с Arduino-ESP32 [1], однако прикладные probe и ACK подтвердили двусторонний обмен на исследованных версиях библиотек. После обновления core или SDK матрицу следует повторять.")
    add_body(doc, "Времена восстановления ESP8266-ESP32 и ESP8266-ESP32-S3 почти совпали: 15,214 и 15,229 с. В предварительной конфигурации встречались интервалы 51-55 с, но после унификации расписания и отключения энергосбережения они не повторились. Это указывает на существенное влияние программных параметров, а не только типа микроконтроллера. Документация Espressif подтверждает, что modem-sleep способен добавлять задержку порядка DTIM или listen interval, тогда как WIFI_PS_NONE уменьшает задержку приёма [11].")
    add_body(doc, "Разнесение UDP и recovery probe оказалось принципиальным для общей радиочасти. Независимые периодические таймеры могут совпадать по фазе и создавать конкуренцию внутри одного poll-цикла. В итоговой версии чередование слотов делает расписание явным и наблюдаемым. Этот вывод согласуется с работами, в которых реальная задержка ESP-NOW зависит не только от радио, но и от программной обработки, планировщика и нагрузки узла [7, 8].")
    add_body(doc, "Результаты UDP требуют осторожной трактовки. RFC 768 определяет минимальный датаграммный сервис без механизма гарантированной доставки [9], а рекомендации RFC 8085 требуют реализовать надёжность на прикладном уровне, если она необходима [10]. Для следующей версии целесообразны ограниченная очередь неподтверждённых сообщений, повтор по таймеру, дедупликация sequence, срок жизни пакета и ограничение числа повторов. CRC32 уже защищает полезную нагрузку и облегчает сопоставление двух транспортов, но не заменяет повторную передачу.")
    add_body(doc, "Работы [4-8] рассматривают ESP-NOW как самостоятельный канал, транспорт датчиков или часть шлюза. В доступной выборке литературы не обнаружена попарная матрица ESP8266, ESP32 и ESP32-S3 с автоматическим переходом на UDP и возвратом по прикладным ACK. В данной работе такая матрица собрана с единым алгоритмом и воспроизводимым журналом. Обзор не доказывает полного отсутствия схожих разработок.")

    add_heading(doc, "4.1 Ограничения исследования", 2)
    add_body(doc, "Исследование выполнено на одном экземпляре каждой платы, одном маршрутизаторе, одном расстоянии и в одной радиосреде. Не измерялись энергопотребление, RSSI, полезная пропускная способность под нагрузкой, влияние препятствий и работа при нескольких активных отправителях. Управляемый отказ подавляет прикладной ACK, но не моделирует физическое экранирование, выключение питания, зависание контроллера или отказ точки доступа.")
    add_body(doc, "Для каждой пары выполнено пять циклов, а направления распределены как три и два повтора. Это позволяет подтвердить воспроизводимость перехода в рамках стенда, но не даёт достаточной мощности для вывода о различиях аппаратных платформ. В одной стандартизированной серии ESP8266-ESP32-S3 подготовительный интервал был короче заданных 30 с, хотя обязательные стабилизационные окна завершились успешно. Поэтому корректно сравнивать времена после команд ACK OFF и ACK ON, но нельзя трактовать различие общего числа baseline probe как аппаратный эффект.")
    add_body(doc, "Не исследована безопасность: ESP-NOW и UDP использовались без прикладной аутентификации и шифрования. Для практического устройства необходимо включить доступные средства защиты peer, а для UDP добавить проверку источника и криптографическую целостность. Также следует испытать обновления программных платформ, поскольку межпоколенческая совместимость зависит от конкретных версий библиотек.")

    add_heading(doc, "5 Заключение", 1)
    add_body(doc, "Разработан программно-аппаратный стенд и единый автомат резервирования для ESP8266, ESP32 и ESP32-S3. Основной ESP-NOW и резервный Wi-Fi/UDP используют общий 20-байтовый пакет с sequence, временем работы и CRC32. Прикладные ACK позволяют отличить локальный результат драйвера от фактического удалённого приёма, а оконный гистерезис исключает частое переключение около порога.")
    add_body(doc, "Во всех трёх аппаратных парах переход ESP-NOW - UDP и возврат UDP - ESP-NOW состоялись в пяти из пяти опытов, всего 15/15 циклов. Базовая доставка составила 843/843 ACK. Средние времена перехода и возврата равны 8,613 и 15,707 с. При этом резервный UDP обеспечил 323/374 ACK, а в паре ESP32-ESP32-S3 только 74/108. Следовательно, работоспособность автомата подтверждена, но гарантированная доставка резерва требует повторов и дедупликации на прикладном уровне.")
    add_body(doc, "Следующий этап должен включать рандомизированные серии по направлениям, несколько расстояний и препятствий, измерение RSSI и энергопотребления, одновременную работу трёх узлов и физические виды отказа. После реализации очереди повторов следует отдельно оценить, как повышение надёжности UDP влияет на задержку, нагрузку радиоканала и время возврата к ESP-NOW.")

    add_heading(doc, "Доступность данных и программного обеспечения", 1)
    add_body(doc, "Исходный код прошивок, настольное приложение, инструкции испытаний, анализаторы, агрегированные JSON и векторные рисунки опубликованы в открытом репозитории: https://github.com/maggogerka/wireless-link-failover. Сырые журналы большого объёма хранятся отдельно; агрегированные сводки содержат их SHA-256. Проект распространяется по лицензии MIT.", first_indent=False)

    add_heading(doc, "Этические и организационные сведения", 1)
    add_body(doc, "Работа является инженерным исследованием беспроводных микроконтроллерных узлов и не включает экспериментов с людьми или животными. Финансирование: работа выполнена без внешнего финансирования. Конфликт интересов: авторы заявляют об отсутствии конфликта интересов. Вклад авторов подлежит уточнению перед подачей статьи.")

    add_heading(doc, "Список литературы", 1)
    references = [
        "Espressif Systems. ESP-NOW - Arduino ESP32 documentation. URL: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/espnow.html (дата обращения: 09.11.2026).",
        "Espressif Systems. ESP-NOW - ESP-IDF Programming Guide. URL: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/network/esp_now.html (дата обращения: 09.11.2026).",
        "Espressif Systems. ESP8266 RTOS SDK Programming Guide. URL: https://docs.espressif.com/projects/esp8266-rtos-sdk/en/latest/ (дата обращения: 09.11.2026).",
        "Becker B., Oberli C., Zobel J., Steinmetz R., Meuser T. ESP-NOW Performance in Outdoor Environments: Field Experiments and Analysis. 2025 20th IEEE/IFIP Wireless On-Demand Network Systems and Services Conference (WONS). 2025. P. 1-8.",
        "Mutiara M., Kusuma H.A., Suhendra T. Field Testing and QoS Analysis of ESP-NOW Communication on ESP32. 2024 FORTEI-International Conference on Electrical Engineering. 2024. DOI: 10.1109/FORTEI-ICEE64706.2024.10824617.",
        "Eridani D., Rochim A.F., Cesara F.N. Comparative Performance Study of ESP-NOW, Wi-Fi, Bluetooth Protocols Based on Range, Transmission Speed, Latency, Energy Usage and Barrier Resistance. iSemantic 2021. P. 322-328. DOI: 10.1109/iSemantic52711.2021.9573246.",
        "Levush P., Luchechko A. Performance Evaluation of ESP-NOW for Low-Latency Indoor IoT Systems. Advances in Cyber-Physical Systems. 2026. Vol. 11, no. 1. P. 1-5. DOI: 10.23939/acps2026.01.001.",
        "Smelcerz K. Characterization of Latency Sources in a MicroPython-Based ESP32 Edge-Cloud Sensor Network. Sensors. 2026. Vol. 26, no. 17. Article 5555. DOI: 10.3390/s26175555.",
        "Postel J. User Datagram Protocol. RFC 768. 1980. DOI: 10.17487/RFC0768. URL: https://www.rfc-editor.org/info/rfc768.",
        "Eggert L., Fairhurst G., Shepherd G. UDP Usage Guidelines. RFC 8085. 2017. DOI: 10.17487/RFC8085.",
        "Espressif Systems. Wi-Fi Performance and Power Save - ESP-IDF Programming Guide. URL: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/wifi-driver/wifi-performance-and-power-save.html (дата обращения: 09.11.2026).",
        "Espressif Systems. ESP8266EX Datasheet. Version 7.1. 2025. URL: https://www.espressif.com/en/support/documents/technical-documents (дата обращения: 09.11.2026).",
        "Espressif Systems. ESP32 Series Datasheet. Version 5.3. 2026. URL: https://www.espressif.com/en/support/documents/technical-documents (дата обращения: 09.11.2026).",
        "Espressif Systems. ESP32-S3 Series Datasheet. Version 2.2. 2026. URL: https://documentation.espressif.com/esp32-s3_datasheet_en.pdf (дата обращения: 09.11.2026).",
        "Bembiev F. Wireless Link Failover: firmware, desktop application and reproducible experiment materials. GitHub repository. URL: https://github.com/maggogerka/wireless-link-failover (дата обращения: 09.11.2026).",
    ]
    for index, reference in enumerate(references, 1):
        add_reference(doc, index, reference)

    doc.add_page_break()
    add_heading(doc, "Сведения об авторах", 1)
    add_table(
        doc, 6, "Сведения об авторах", "Author information",
        ["Автор", "Сведения для заполнения"],
        [
            ["Автор 1", "Бембиев Феликс Эдуардович; студент института №14 «Передовая инженерная школа» Московского авиационного института (национального исследовательского университета)"],
            ["Автор 2", "Кадеров Владимир Андреевич; сведения и должность уточнить перед подачей"],
        ],
        [1.25, 5.17],
        [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT],
        9.5,
    )

    add_heading(doc, "English metadata", 1)
    english_title = doc.add_paragraph(style="Normal")
    english_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    english_title.paragraph_format.first_line_indent = Cm(0)
    run = english_title.add_run("Intergenerational ESP-NOW Compatibility and Automatic UDP Failover in a Heterogeneous ESP8266, ESP32 and ESP32-S3 Network")
    set_run_font(run, 13, bold=False)
    english_authors = doc.add_paragraph(style="Normal")
    english_authors.alignment = WD_ALIGN_PARAGRAPH.CENTER
    english_authors.paragraph_format.first_line_indent = Cm(0)
    run = english_authors.add_run("AUTHOR 1: Bembiev F.E.     AUTHOR 2: Kaderov V.A.\nMoscow Aviation Institute, Moscow, Russia")
    set_run_font(run, 11)
    english_abstract = (
        "Abstract. This paper investigates intergenerational ESP-NOW compatibility and presents an automatic Wi-Fi/UDP failover mechanism for ESP8266, ESP32 and ESP32-S3 nodes. Both transports use the same 20-byte packet with sequence number, uptime and CRC32, while delivery is evaluated by application-level acknowledgements. ESP-NOW is the primary transport and UDP through a 2.4 GHz access point is the reserve. The state machine uses non-overlapping windows and hysteresis: two degraded windows trigger fallback and three qualifying recovery windows return the sender to ESP-NOW. Five controlled cycles were completed for each of the three hardware pairs at a distance of approximately 1 m with Wi-Fi power saving disabled. All 15 cycles completed both fallback and recovery. Baseline ESP-NOW delivery was 843/843 acknowledgements. Mean fallback and recovery times were 8.613 s and 15.707 s. Reserve UDP delivered 323/374 acknowledgements overall, but only 74/108 for the ESP32-ESP32-S3 pair. The results demonstrate reproducible operation of one transport-selection algorithm across three device generations, while also showing that successful state transition must not be interpreted as guaranteed UDP delivery. Application-level retries and deduplication are required for a reliable reserve channel."
    )
    add_body(doc, english_abstract, first_indent=False)
    keywords_en = doc.add_paragraph(style="Normal")
    keywords_en.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    keywords_en.paragraph_format.first_line_indent = Cm(0)
    run = keywords_en.add_run("Keywords: ")
    set_run_font(run, 10, bold=True)
    run = keywords_en.add_run("ESP-NOW, UDP, ESP8266, ESP32, ESP32-S3, failover, heterogeneous embedded network, Internet of Things.")
    set_run_font(run, 10)

    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
