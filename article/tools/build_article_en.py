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
from docx.shared import Cm, Inches, Pt

from build_article_ru import (
    ASSETS,
    EXPECTED_REFERENCE_HASH,
    REFERENCE,
    REPO,
    add_body,
    add_heading,
    add_reference,
    ensure_black_styles,
    prevent_row_split,
    remove_document_body,
    repeat_header,
    set_cell_margins,
    set_cell_shading,
    set_repeat_table_layout,
    set_run_font,
    set_table_borders,
)


OUTPUT = Path(os.environ.get("WLF_ARTICLE_EN_OUTPUT", REPO / "article" / "Wireless_Link_Failover_article_en.docx"))


def add_figure_en(doc, filename, width, caption_text):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Cm(0)
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    picture = paragraph.add_run().add_picture(str(ASSETS / filename), width=Inches(width))
    picture._inline.docPr.set("title", filename)
    picture._inline.docPr.set("descr", caption_text)
    caption = doc.add_paragraph(style="Caption")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.first_line_indent = Cm(0)
    caption.paragraph_format.keep_together = True
    run = caption.add_run(caption_text)
    set_run_font(run, 9, bold=True)
    return caption


def add_table_en(doc, number, title, headers, rows, widths, aligns=None, font_size=9.5):
    caption = doc.add_paragraph(style="Normal")
    caption.alignment = WD_ALIGN_PARAGRAPH.LEFT
    caption.paragraph_format.first_line_indent = Cm(0)
    caption.paragraph_format.space_before = Pt(4)
    caption.paragraph_format.space_after = Pt(2)
    caption.paragraph_format.keep_with_next = True
    run = caption.add_run(f"Table {number}. {title}")
    set_run_font(run, 10, bold=True)
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_repeat_table_layout(table, [Inches(value) for value in widths])
    set_table_borders(table, color="D9D9D9", size="6")
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
    for values in rows:
        cells = table.add_row().cells
        prevent_row_split(table.rows[-1])
        for column, value in enumerate(values):
            cell = cells[column]
            cell.width = Inches(widths[column])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            set_cell_shading(cell, "FFFFFF")
            paragraph = cell.paragraphs[0]
            paragraph.alignment = aligns[column] if aligns else WD_ALIGN_PARAGRAPH.LEFT
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


def build():
    current_hash = hashlib.sha256(REFERENCE.read_bytes()).hexdigest().upper()
    if current_hash != EXPECTED_REFERENCE_HASH:
        raise RuntimeError(f"Reference hash changed: {current_hash}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REFERENCE, OUTPUT)
    doc = Document(OUTPUT)
    remove_document_body(doc)
    ensure_black_styles(doc)
    doc.core_properties.title = "Intergenerational ESP-NOW Compatibility and Automatic UDP Failover"
    doc.core_properties.subject = "ESP8266, ESP32 and ESP32-S3 failover from ESP-NOW to Wi-Fi/UDP"
    doc.core_properties.author = "Bembiev F.E.; Kaderov V.A."
    doc.core_properties.keywords = "ESP-NOW, UDP, ESP8266, ESP32, ESP32-S3, failover, embedded systems"

    title = doc.add_paragraph(style="Article Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.keep_with_next = True
    run = title.add_run("Intergenerational ESP-NOW Compatibility and Automatic UDP Failover in a Heterogeneous ESP8266, ESP32 and ESP32-S3 Network")
    set_run_font(run, 15, bold=True)

    authors = doc.add_paragraph(style="Normal")
    authors.alignment = WD_ALIGN_PARAGRAPH.CENTER
    authors.paragraph_format.first_line_indent = Cm(0)
    authors.paragraph_format.space_after = Pt(2)
    run = authors.add_run("AUTHOR 1: Bembiev F.E.     AUTHOR 2: Kaderov V.A.")
    set_run_font(run, 11, bold=True)
    affiliation = doc.add_paragraph(style="Normal")
    affiliation.alignment = WD_ALIGN_PARAGRAPH.CENTER
    affiliation.paragraph_format.first_line_indent = Cm(0)
    affiliation.paragraph_format.space_after = Pt(8)
    run = affiliation.add_run("Moscow Aviation Institute, Moscow, Russia")
    set_run_font(run, 11)

    add_body(doc, (
        "This paper evaluates intergenerational ESP-NOW compatibility and an automatic Wi-Fi/UDP failover mechanism for ESP8266, ESP32 and ESP32-S3 nodes. Both transports carry the same 20-byte packet containing a sequence number, sender uptime and CRC32. Delivery is measured with application-level acknowledgements rather than the local radio callback. ESP-NOW is the primary transport; UDP through a 2.4 GHz access point is the reserve. A windowed state machine uses two degraded windows to enter UDP and three qualifying recovery windows to return to ESP-NOW. Five controlled cycles were completed for each of the three hardware pairs at a distance of approximately 1 m with Wi-Fi power saving disabled. All 15 cycles completed fallback and recovery. Baseline ESP-NOW delivery was 843/843 acknowledgements. Mean fallback and recovery times were 8.613 s and 15.707 s. Reserve UDP delivered 323/374 acknowledgements overall, including 74/108 for the ESP32-ESP32-S3 pair. The state machine therefore operated reproducibly on the tested software versions, but the reserve path requires application-level retransmission and deduplication when delivery guarantees are needed."
    ), first_indent=False)
    keywords = doc.add_paragraph(style="Normal")
    keywords.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    keywords.paragraph_format.first_line_indent = Cm(0)
    keywords.paragraph_format.space_after = Pt(8)
    run = keywords.add_run("Keywords: ")
    set_run_font(run, 10, bold=True)
    run = keywords.add_run("ESP-NOW, UDP, ESP8266, ESP32, ESP32-S3, transport failover, heterogeneous embedded network, Internet of Things.")
    set_run_font(run, 10)

    add_heading(doc, "1 Introduction", 1)
    add_body(doc, "Wireless microcontroller nodes are used in distributed sensors, control systems, teaching equipment and Internet of Things devices. Low delay and low hardware cost are useful in these systems, but the link must also continue to carry traffic when its primary transport degrades. Practical installations often contain boards from several generations that use different microcontrollers and software stacks.")
    add_body(doc, "ESP-NOW transfers short frames directly between devices without requiring an access point. It shares the Wi-Fi radio and offers low protocol overhead for local traffic. Espressif states that the Arduino-ESP32 ESP-NOW library is tested on the ESP32 family, while interoperability with ESP8266 is not guaranteed [1]. The API also requires channel coordination: a peer channel of zero uses the current station or access-point channel [2]. Mixed-generation operation must therefore be verified on hardware and on specific library versions.")
    add_body(doc, "Published experiments report ESP-NOW range, delay, jitter, power consumption and packet loss. Field measurements show that delivery changes with distance and environment [4, 5], while comparative studies identify delay and energy advantages over selected Wi-Fi and Bluetooth configurations [6]. Multi-node and gateway uses have also been examined [7, 8]. These studies do not establish whether one state machine can move all pairwise combinations of ESP8266, ESP32 and ESP32-S3 between direct ESP-NOW and infrastructure UDP.")
    add_body(doc, "UDP was selected as the reserve because all three software environments support it and can reuse the application packet. UDP does not provide retransmission, ordering or duplicate suppression [9, 10]. A successful state transition is therefore different from successful delivery of reserve traffic. The experiment records both outcomes separately.")
    add_body(doc, "The objective was to implement and test one ESP-NOW to UDP to ESP-NOW failover mechanism on ESP8266, ESP32 and ESP32-S3. The tested design uses one packet format, application acknowledgements, CRC and sequence checks, windowed hysteresis, separated radio slots, a desktop control interface and a controlled-failure procedure. The experimental matrix contains 15 cycles across three hardware pairs. It does not cover long-range links, deliberate interference, complete power loss or three simultaneous senders.")

    add_heading(doc, "2 Materials and Methods", 1)
    add_heading(doc, "2.1 Hardware and software", 2)
    add_body(doc, "The testbed used three development boards. The ESP8266 node contains an ESP-12E module; the ESP32 node uses an ESP32-D0WD-V3; and the third node uses an ESP32-S3-N16R8. Firmware was built in Visual Studio Code with PlatformIO. The ESP8266 build used Espressif 8266 Platform 4.2.1 and Arduino Core 3.1.2. ESP32 and ESP32-S3 used Espressif 32 Platform 8.0.0, Arduino Core 3.3.12 and ESP-IDF 5.5.5. The control application and log analyzers used Python 3.11.")
    add_figure_en(doc, "hardware_nodes.png", 6.25, "Fig. 1. Hardware nodes used in the experiment")
    add_table_en(doc, 1, "Experimental testbed components",
        ["Component", "Implementation", "Role"],
        [
            ["ESP8266", "NodeMCU 1.0, ESP-12E, 80 MHz, 4 MB flash", "Intergenerational node 1"],
            ["ESP32", "38-pin DevKit, ESP32-D0WD-V3, dual core, 240 MHz", "Intergenerational node 2"],
            ["ESP32-S3", "DevKitC-compatible, N16R8, dual core, 240 MHz", "Intergenerational node 3"],
            ["Access point", "Huawei WiFi AX1 / WS5203", "UDP, 2.4 GHz, channel 6"],
            ["Computer", "Windows, VS Code, PlatformIO, Python 3.11", "Firmware, GUI and JSONL capture"],
        ], [1.05, 2.75, 2.62],
        [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT], 9.2)
    add_body(doc, "During the reported series, the boards were placed approximately 100 cm apart on a non-metallic surface. Both active nodes joined the neutral laboratory network Lab-2G in the 2.4 GHz band; telemetry recorded channel 6. Wi-Fi power saving was disabled. This increases power consumption but reduces receive delay and removes the dependence on DTIM. Espressif documents WIFI_PS_NONE as the mode for minimum real-time receive delay [11].")

    add_heading(doc, "2.2 Communication architecture", 2)
    add_body(doc, "Each experiment used one hardware pair; the third board did not exchange traffic. The active sender generated probes, and the receiver validated each packet and returned an application ACK. ESP-NOW was the primary direct transport. UDP was started on the same nodes and passed through the access point: probes were broadcast on the local subnet and ACKs returned by unicast to the sender. A computer sent commands over USB Serial and wrote events from both boards to one JSON Lines log.")
    add_figure_en(doc, "architecture_en.png", 6.25, "Fig. 2. Architecture of the experimental testbed")
    add_body(doc, "ESP-NOW and infrastructure Wi-Fi share one radio channel. After the station joined the access point, the firmware read the current channel and registered the ESP-NOW broadcast peer again with channel zero. Channel zero selects the station interface channel [2]. This removed a hidden channel mismatch and allowed the application transport to change without reconfiguring the radio.")

    add_heading(doc, "2.3 Packet format and application acknowledgements", 2)
    add_body(doc, "Both transports use one packed, little-endian structure of 20 bytes. The receiver checks length, magic value, version and CRC32. Radio callbacks only copy events into a static queue; JSON construction and serial output occur in the main loop. This keeps the Wi-Fi callback short and makes telemetry comparable on devices with different memory limits.")
    add_table_en(doc, 2, "Experimental packet format",
        ["Offset", "Size", "Field", "Purpose"],
        [
            ["0", "4", "magic", "WLF1 signature"],
            ["4", "1", "version", "Format version, value 1"],
            ["5", "1", "messageType", "1 = probe; 2 = ACK"],
            ["6", "1", "senderNode", "1 = ESP8266; 2 = ESP32; 3 = ESP32-S3"],
            ["7", "1", "flags", "Application-ACK destination"],
            ["8", "4", "sequence", "Monotonic transmission number"],
            ["12", "4", "senderUptimeMs", "Sender millis() value"],
            ["16", "4", "crc32", "CRC32 of bytes 0-15, polynomial 0xEDB88320"],
        ], [0.7, 0.62, 1.25, 3.85],
        [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT], 8.9)
    add_body(doc, "The local driver result for a broadcast frame was not treated as proof of remote reception. The receiver instead sent an ACK packet of type 2 with the probe sequence number. The sender matched the ACK against a ring buffer of recent messages and calculated round-trip time. UDP used the same fields and checks, so delivery was compared at one application layer.")

    add_heading(doc, "2.4 Transport selection state machine", 2)
    add_body(doc, "The state machine evaluates application ACKs in non-overlapping windows. Three windows after startup stabilize the baseline and cannot trigger a transition. In the primary state, an ESP-NOW probe is sent every 470 ms. Two consecutive 5000 ms windows with at least 30% loss select UDP. ESP-NOW recovery probes continue while UDP carries application traffic. Three windows with at least 80% ESP-NOW ACKs return the sender to the primary transport.")
    add_figure_en(doc, "state_machine_en.png", 6.25, "Fig. 3. Transport selection state machine")
    add_table_en(doc, 3, "Standardized state-machine parameters",
        ["Parameter", "Value", "Purpose"],
        [
            ["Primary probe period", "470 ms", "ESP-NOW observation rate"],
            ["Evaluation window", "5000 ms", "Non-overlapping statistics interval"],
            ["Fallback threshold", "loss ≥ 30%", "Qualifies a degraded window"],
            ["Degraded windows", "2", "Hysteresis before UDP"],
            ["Recovery probe", "940 ms", "ESP-NOW check while UDP is active"],
            ["Offset / guard", "235 / 470 ms", "Separates transmissions on the shared radio"],
            ["Recovery threshold", "ACK ≥ 80%", "Qualifies a recovery window"],
            ["Recovery windows", "3", "Hysteresis before return"],
        ], [2.35, 1.25, 2.82],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT], 9.0)
    add_body(doc, "UDP and ESP-NOW share one radio. Early diagnostic runs used independent timers that could schedule both transmissions in one poll cycle and reduce recovery ACKs. The final scheduler offsets recovery probes by 235 ms and applies a 470 ms guard, producing alternating UDP and ESP-NOW slots. If infrastructure Wi-Fi becomes unavailable, the firmware selects ESP-NOW because UDP cannot continue without the access point.")

    add_heading(doc, "2.5 Experiment control and logging", 2)
    add_body(doc, "The desktop application discovers serial ports, assigns sender and receiver roles, connects nodes to Wi-Fi, configures the state machine and controls ACK suppression. The failure command is disabled until the preparation interval has elapsed. Events including radio_info, wifi_status, failover_window, failover_transition, fault_control and udp_info are written with host timestamps. The Wi-Fi password is sent only to volatile device memory and is omitted from the log.")
    add_figure_en(doc, "console.png", 6.25, "Fig. 4. Experiment control and logging interface")
    add_body(doc, "For each accepted repeat, the analyzer extracts one complete cycle from failover_enabled through the return to ESP-NOW. It verifies event order and calculates baseline delivery, fallback reaction time, recovery reaction time, UDP delivery and final recovery windows. Each aggregate JSON records the source snapshot path and SHA-256 digest, linking reported values to an immutable copy of the primary log even when the large JSONL file is not stored in Git.")

    add_heading(doc, "2.6 Experimental procedure", 2)
    add_body(doc, "Five controlled cycles were completed for each hardware pair. One node was the active sender and the other the passive receiver. After joining the access point, the operator reset statistics, enabled the state machine and established the baseline. The ESPNOW ACK OFF command then suppressed only application ESP-NOW acknowledgements on the receiver. Power, radio hardware, Wi-Fi and UDP remained operational. The procedure models logical degradation of the primary transport rather than complete node failure.")
    add_figure_en(doc, "timeline_en.png", 6.25, "Fig. 5. Standardized controlled-failure cycle")
    add_body(doc, "After automatic fallback, UDP reserve operation was recorded. The ESPNOW ACK ON command restored application acknowledgements, after which the state machine had to accumulate three recovery windows and return without manual transport selection. For ESP32-ESP32-S3, the GUI enforced a 30 s guard; device timestamps gave preparation intervals of 29.691-48.943 s within a 1 s host/device tolerance and at least five completed windows. The ESP8266-ESP32-S3 series enabled the fault earlier, after 16.284-26.429 s, but all repeats completed the three stabilization windows with 100% ACKs. The deviation is retained in the data and limits comparisons of total baseline counts.")

    add_heading(doc, "2.7 Metrics and descriptive statistics", 2)
    add_body(doc, "The metrics were baseline ACK delivery, completion of fallback and recovery, reaction time after ACK OFF and ACK ON, reserve UDP ACK delivery, ACK delivery in final recovery windows and time spent in UDP. Minimum, mean, median, maximum and sample standard deviation were calculated for reaction times. Five repeats per pair demonstrate repeatability of the algorithm within this testbed but do not provide sufficient power for claims of platform superiority or directional asymmetry. Results are therefore descriptive; no hypothesis tests were applied.")

    add_heading(doc, "3 Results", 1)
    add_heading(doc, "3.1 Preliminary ESP-NOW compatibility", 2)
    add_body(doc, "Bidirectional ESP-NOW series were completed before testing failover. ESP32 and ESP32-S3 delivered 1000/1000 application ACKs in each direction. Two 1000-packet series between ESP32 and ESP8266 delivered 1998/2000 and 1988/2000 ACKs in opposite directions. ESP8266 and ESP32-S3 delivered 1999/2000 and 1952/2000 ACKs in the initial close-range placement. All three generations exchanged application packets, although delivery depended on direction and conditions. This observation is specific to the tested software and does not replace the ESP8266 compatibility warning [1].")
    add_body(doc, "A separate test confirmed ESP-NOW operation while both nodes were associated with the access point on channel 6. This is required for the failover design: a different ESP-NOW channel would require radio retuning during fallback and introduce an uncontrolled interval. The baseline was stable in every reported cycle.")

    add_heading(doc, "3.2 Pairwise failover matrix", 2)
    add_table_en(doc, 4, "Results for each hardware pair",
        ["Pair", "Fallback / recovery", "ESP-NOW baseline", "Fallback, s", "Recovery, s", "UDP ACK"],
        [
            ["ESP8266-ESP32", "5/5", "308/308", "7.689", "15.214", "120/133 (90.226%)"],
            ["ESP8266-ESP32-S3", "5/5", "193/193", "8.284", "15.229", "129/133 (96.992%)"],
            ["ESP32-ESP32-S3", "5/5", "342/342", "9.867", "16.678", "74/108 (68.519%)"],
        ], [1.35, 1.0, 1.0, 0.85, 0.85, 1.37],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER], 8.4)
    add_body(doc, "The state machine detected degradation, selected UDP and returned to ESP-NOW in all 15 cycles. Baseline delivery was 843/843 ACKs. Across all cycles, mean fallback time was 8.613 s, the median was 8.405 s, the range was 6.678-11.500 s and the sample standard deviation was 1.575 s. Mean recovery time was 15.707 s, the median was 14.851 s, the range was 13.848-18.392 s and the standard deviation was 1.732 s.")
    add_figure_en(doc, "results_en.png", 6.35, "Fig. 6. Reaction times and UDP application-ACK delivery for the three hardware pairs")
    add_body(doc, "The reaction times follow the state-machine rules. Two degraded 5 s windows produce a nominal detection interval of about 10 s; the observed variation depends on the phase of the current window when ACK OFF is issued. Three recovery windows produce a minimum interval near 15 s. One ESP8266-ESP32-S3 cycle remained in UDP for 40.036 s, but every cycle returned automatically.")

    add_heading(doc, "3.3 Reserve UDP delivery", 2)
    add_body(doc, "Reserve UDP delivered 323 of 374 observed application ACKs, or 86.364%. Delivery differed across pairs: 90.226% for ESP8266-ESP32, 96.992% for ESP8266-ESP32-S3 and 68.519% for ESP32-ESP32-S3. The lower value in the third pair did not prevent recovery. After ACK ON, that pair delivered 79/80 ESP-NOW ACKs in its final recovery windows; the complete matrix delivered 232/240, or 96.667%.")
    add_body(doc, "The acceptance criteria separate state-machine operation from reserve-traffic delivery. A cycle passes the transition criterion when telemetry contains fallback and recovery. UDP quality is measured from its own ACKs. The result of 74/108 for ESP32-ESP32-S3 means that the current prototype is not a guaranteed-delivery channel. It provides a reserve route and continued attempts, but individual datagrams can be lost.")

    add_heading(doc, "3.4 ESP32 and ESP32-S3 directions", 2)
    add_table_en(doc, 5, "Directions in the ESP32-ESP32-S3 series",
        ["Sender", "Repeats", "Fallback, s", "Recovery, s", "UDP ACK"],
        [
            ["ESP32 → ESP32-S3", "3", "9.562", "17.027", "45/71 (63.380%)"],
            ["ESP32-S3 → ESP32", "2", "10.324", "16.154", "29/37 (78.378%)"],
        ], [1.85, 0.85, 1.15, 1.15, 1.42],
        [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER], 9.0)
    add_body(doc, "UDP delivery differed by about 15 percentage points between directions, but the comparison contains only three repeats in one direction and two in the other, with different packet counts. It identifies a question for the next experiment rather than established hardware asymmetry. A directional comparison requires at least five repeats per direction in randomized order with access-point load controlled.")

    add_heading(doc, "4 Discussion", 1)
    add_body(doc, "One algorithm completed fallback and recovery on all three pairwise combinations of ESP8266, ESP32 and ESP32-S3. The official documentation does not guarantee ESP8266 interoperability with Arduino-ESP32 [1], but the application probes and ACKs confirmed bidirectional operation on the tested library versions. The pairwise matrix should be repeated after a core or SDK update.")
    add_body(doc, "Recovery times for ESP8266-ESP32 and ESP8266-ESP32-S3 were nearly identical at 15.214 s and 15.229 s. Preliminary configurations had produced 51-55 s intervals, but those values did not recur after the schedule was standardized and Wi-Fi power saving was disabled. Software timing therefore affected the result. Espressif documents that modem sleep can add delay on the order of the DTIM or listen interval, whereas WIFI_PS_NONE reduces receive delay [11].")
    add_body(doc, "Separating UDP and recovery-probe slots was important because both transports use the same radio. Independent periodic timers can align and compete within one poll cycle. Alternating slots make the schedule explicit and observable. This agrees with reports that measured ESP-NOW latency includes software processing, scheduler behavior and device load as well as radio propagation [7, 8].")
    add_body(doc, "RFC 768 defines UDP as a minimal datagram service without guaranteed delivery [9]. RFC 8085 requires applications to implement reliability when they need it [10]. The next implementation should use a bounded queue of unacknowledged messages, timer-based retransmission, sequence deduplication, packet lifetime and a retry limit. CRC32 detects payload corruption and supports transport comparison, but it does not replace retransmission.")
    add_body(doc, "References [4-8] treat ESP-NOW as a stand-alone link, a sensor transport or part of a gateway. Within the reviewed sample, no study reported a pairwise ESP8266, ESP32 and ESP32-S3 matrix with automatic UDP fallback and return based on application ACKs. The present work supplies that matrix with one algorithm and a reproducible event log. The literature search does not establish that no similar implementation exists elsewhere.")

    add_heading(doc, "4.1 Limitations", 2)
    add_body(doc, "The experiment used one board of each type, one access point, one distance and one radio environment. It did not measure energy consumption, RSSI, useful throughput under load, obstacles or multiple active senders. The controlled fault suppresses an application ACK; it does not model shielding, power loss, firmware lockup or access-point failure.")
    add_body(doc, "Each hardware pair has five cycles, and sender directions are split into three and two repeats. The sample confirms repeatability within this testbed but is too small to attribute differences to hardware. In one standardized ESP8266-ESP32-S3 series, the preparation interval was shorter than the requested 30 s even though the required stabilization windows completed successfully. Reaction times after ACK OFF and ACK ON remain comparable; total baseline probe counts should not be interpreted as a platform effect.")
    add_body(doc, "Security was outside the experiment. ESP-NOW and UDP were used without application authentication or encryption. A deployed system should enable available peer protection and add source validation and cryptographic integrity to UDP. Software-platform updates also require renewed compatibility tests because the result depends on specific library versions.")

    add_heading(doc, "5 Conclusion", 1)
    add_body(doc, "The implemented testbed uses one failover state machine on ESP8266, ESP32 and ESP32-S3. Primary ESP-NOW and reserve Wi-Fi/UDP carry one 20-byte packet with sequence number, sender uptime and CRC32. Application ACKs distinguish the local radio callback from remote reception, and windowed hysteresis prevents repeated switching near one threshold.")
    add_body(doc, "All three hardware pairs completed fallback and recovery in five of five cycles, giving 15/15 complete cycles. Baseline delivery was 843/843 ACKs. Mean fallback and recovery times were 8.613 s and 15.707 s. Reserve UDP delivered 323/374 ACKs overall and 74/108 in the ESP32-ESP32-S3 pair. The transition algorithm is reproducible in the tested setup; reliable reserve delivery still requires application retransmission and deduplication.")
    add_body(doc, "Further tests should randomize sender direction, add distances and obstacles, measure RSSI and power, run three active nodes and introduce physical failures. After a retry queue is implemented, its effect on latency, radio load and recovery time should be measured separately.")

    add_heading(doc, "Data and software availability", 1)
    add_body(doc, "Firmware, the desktop application, test instructions, analyzers, aggregate JSON files and vector figures are available at https://github.com/maggogerka/wireless-link-failover. Large raw logs are stored separately; aggregate summaries record their SHA-256 digests. The project is released under the MIT License.", first_indent=False)

    add_heading(doc, "Ethics, funding and conflicts of interest", 1)
    add_body(doc, "This engineering study of wireless microcontroller nodes did not involve human participants or animals. The work received no external funding. The authors declare no conflict of interest. Author contributions should be completed before journal submission.")

    add_heading(doc, "References", 1)
    references = [
        "Espressif Systems. ESP-NOW - Arduino ESP32 documentation. https://docs.espressif.com/projects/arduino-esp32/en/latest/api/espnow.html (accessed 9 November 2026).",
        "Espressif Systems. ESP-NOW - ESP-IDF Programming Guide. https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/network/esp_now.html (accessed 9 November 2026).",
        "Espressif Systems. ESP8266 RTOS SDK Programming Guide. https://docs.espressif.com/projects/esp8266-rtos-sdk/en/latest/ (accessed 9 November 2026).",
        "Becker B., Oberli C., Zobel J., Steinmetz R., Meuser T. ESP-NOW Performance in Outdoor Environments: Field Experiments and Analysis. 2025 20th IEEE/IFIP Wireless On-Demand Network Systems and Services Conference. 2025. pp. 1-8.",
        "Mutiara M., Kusuma H.A., Suhendra T. Field Testing and QoS Analysis of ESP-NOW Communication on ESP32. 2024 FORTEI-International Conference on Electrical Engineering. DOI: 10.1109/FORTEI-ICEE64706.2024.10824617.",
        "Eridani D., Rochim A.F., Cesara F.N. Comparative Performance Study of ESP-NOW, Wi-Fi, Bluetooth Protocols Based on Range, Transmission Speed, Latency, Energy Usage and Barrier Resistance. iSemantic 2021. pp. 322-328. DOI: 10.1109/iSemantic52711.2021.9573246.",
        "Levush P., Luchechko A. Performance Evaluation of ESP-NOW for Low-Latency Indoor IoT Systems. Advances in Cyber-Physical Systems. 2026;11(1):1-5. DOI: 10.23939/acps2026.01.001.",
        "Smelcerz K. Characterization of Latency Sources in a MicroPython-Based ESP32 Edge-Cloud Sensor Network. Sensors. 2026;26(17):5555. DOI: 10.3390/s26175555.",
        "Postel J. User Datagram Protocol. RFC 768. 1980. DOI: 10.17487/RFC0768. https://www.rfc-editor.org/info/rfc768.",
        "Eggert L., Fairhurst G., Shepherd G. UDP Usage Guidelines. RFC 8085. 2017. DOI: 10.17487/RFC8085.",
        "Espressif Systems. Wi-Fi Performance and Power Save - ESP-IDF Programming Guide. https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/wifi-driver/wifi-performance-and-power-save.html (accessed 9 November 2026).",
        "Espressif Systems. ESP8266EX Datasheet. Version 7.1. 2025. https://www.espressif.com/en/support/documents/technical-documents.",
        "Espressif Systems. ESP32 Series Datasheet. Version 5.3. 2026. https://www.espressif.com/en/support/documents/technical-documents.",
        "Espressif Systems. ESP32-S3 Series Datasheet. Version 2.2. 2026. https://documentation.espressif.com/esp32-s3_datasheet_en.pdf.",
        "Bembiev F. Wireless Link Failover: firmware, desktop application and reproducible experiment materials. GitHub repository. https://github.com/maggogerka/wireless-link-failover (accessed 9 November 2026).",
    ]
    for index, reference in enumerate(references, 1):
        add_reference(doc, index, reference)

    doc.add_page_break()
    add_heading(doc, "Author information", 1)
    add_table_en(doc, 6, "Author information",
        ["Author", "Information"],
        [
            ["Author 1", "Felix Eduardovich Bembiev; student, Institute No. 14, Advanced Engineering School, Moscow Aviation Institute"],
            ["Author 2", "Vladimir Andreevich Kaderov; affiliation and position to be confirmed before submission"],
        ], [1.25, 5.17], [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT], 9.5)

    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
