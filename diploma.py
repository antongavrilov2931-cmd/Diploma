import re
import os
import sys
import random
from typing import Optional, List
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import heapq
from enum import Enum

os.system("chcp 65001 > nul")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except:
    pass

# КОНСТАНТЫ
C_MS = 299792458
C_KM_PER_NS = 299792458 / 1e9 / 1000  
DISCRETE_NS = 20
TACT_NS = 52_428_800
STATIONS = 2
PROCESSING_FACTOR = 1.0

# Максимальное число кандидатов, просматриваемых при поиске лучшей пары
MAX_PAIR_SEARCH = 60


# КЛАСС ЗАЯВКИ
class RadarRequest:
    PRIO_SEARCH  = [1000, 19000]
    PRIO_TRACK   = [4000, 8000, 10000, 12000, 13000]
    PRIO_ACQUIRE = 14000
    PRIO_JAM     = 0

    def __init__(self, req_id, tgel_ns, tipz, n_tay, n_dfm,
                 rnstr, dstr, dlstr, tpred_ns=None):
        self.req_id  = req_id
        self.tgel_ns = tgel_ns
        self.tipz    = tipz
        self.n_tay   = n_tay
        self.n_dfm   = n_dfm
        self.rnstr   = rnstr
        self.dstr    = dstr
        self.dlstr   = dlstr

        if   tipz == 141: self.priority = self.PRIO_JAM
        elif tipz == 71:  self.priority = random.choice(self.PRIO_SEARCH)
        elif tipz == 75:  self.priority = self.PRIO_ACQUIRE
        elif tipz == 76:  self.priority = random.choice(self.PRIO_TRACK)
        else:             self.priority = 0

        self.emission_duration_ns   = 0
        self.reception_duration_ns  = 0
        self.processing_duration_ns = 0
        self.calculate_durations()

        if tpred_ns is None:
            self.deadline_ns = self.tgel_ns + 2 * TACT_NS
        else:
            self.deadline_ns = tpred_ns   # уже абсолютное время

        self.actual_emit_start = -1
        self.actual_emit_end   = -1
        self.actual_recv_start = -1
        self.actual_recv_end   = -1
        self.actual_proc_start = -1
        self.actual_proc_end   = -1
        self.assigned_station  = -1

    def calculate_durations(self):
       
        if self.tipz == 141:
            self.emission_duration_ns = 0
        else:
            self.emission_duration_ns = int(self.n_tay * self.n_dfm * 1000)

        if self.dlstr is not None:
            
            self.reception_duration_ns = self.dlstr * DISCRETE_NS

        elif self.rnstr is not None and self.dstr is not None:
            propagation_near_ns = int(2 * self.rnstr / C_KM_PER_NS)

            strobe_ns = int(2 * self.dstr / C_KM_PER_NS) if self.dstr > 0 else 0

            guard_ns = max(0, propagation_near_ns - self.emission_duration_ns)

            self.reception_duration_ns = guard_ns + strobe_ns

        else:
            self.reception_duration_ns = self.emission_duration_ns * 2

        self.processing_duration_ns = int(self.reception_duration_ns * PROCESSING_FACTOR)

    def total_duration_ns(self) -> int:
        return (self.emission_duration_ns
                + self.reception_duration_ns
                + self.processing_duration_ns)

    def joint_duration_ns(self, other: "RadarRequest") -> int:
        return (max(self.emission_duration_ns,   other.emission_duration_ns)
              + max(self.reception_duration_ns,  other.reception_duration_ns)
              + max(self.processing_duration_ns, other.processing_duration_ns))

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority > other.priority  
        return self.deadline_ns < other.deadline_ns

    def __repr__(self):
        return (f"Req({self.req_id}, tipz={self.tipz}, prio={self.priority}, "
                f"tgel={self.tgel_ns//TACT_NS}T, dead={self.deadline_ns//TACT_NS}T, "
                f"emit={self.emission_duration_ns/1e6:.2f}ms, "
                f"recv={self.reception_duration_ns/1e6:.2f}ms, "
                f"total={self.total_duration_ns()/1e6:.2f}ms)")


def parse_log(filename: str) -> list:
    requests = []
    p_tgel  = re.compile(r"tgel:\s*(\d+)")
    p_req   = re.compile(r"request_number:\s*(\d+)")
    p_tipz  = re.compile(r"tipz:\s*(\d+)")
    p_auto  = re.compile(r"is_autotest:\s*(\d+)")
    p_n_tay = re.compile(r"parsig::n_tay:\s*([\d.]+)")
    p_n_dfm = re.compile(r"parsig::n_dfm:\s*(\d+)")
    p_rnstr = re.compile(r"rnstr:\s*([\d.]+)")
    p_dstr  = re.compile(r"dstr:\s*([\d.]+)")
    p_dlstr = re.compile(r"dlstr:\s*(\d+)")
    p_tpred = re.compile(r"tpred:\s*(\d+)")

    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                if len(line) < 10:
                    continue
                m_tgel = p_tgel.search(line)
                m_req  = p_req.search(line)
                m_tipz = p_tipz.search(line)
                if not (m_tgel and m_req and m_tipz):
                    continue
                m_auto = p_auto.search(line)
                if m_auto and int(m_auto.group(1)) == 1:
                    continue

                def g(p, cast=str):
                    m = p.search(line)
                    return cast(m.group(1)) if m else None

                requests.append(RadarRequest(
                    req_id   = int(m_req.group(1)),
                    tgel_ns  = int(m_tgel.group(1)),
                    tipz     = int(m_tipz.group(1)),
                    n_tay    = float(g(p_n_tay) or 1.0),
                    n_dfm    = int(g(p_n_dfm) or 1),
                    rnstr    = float(g(p_rnstr)) if g(p_rnstr) else None,
                    dstr     = float(g(p_dstr))  if g(p_dstr)  else None,
                    dlstr    = int(g(p_dlstr))   if g(p_dlstr) else None,
                    tpred_ns = int(g(p_tpred))   if g(p_tpred) else None,
                ))
    except FileNotFoundError:
        print(f"Предупреждение: файл {filename} не найден.")
    return requests


class GlobalState(Enum):
    IDLE     = 0
    TRANSMIT = 1
    RECEIVE  = 2
    PROCESS  = 3


class Event:
    def __init__(self, time_ns, etype, data=None):
        self.time_ns = time_ns
        self.etype   = etype
        self.data    = data

    def __lt__(self, other):
        return self.time_ns < other.time_ns


def next_tact_start(time_ns: int) -> int:
    if time_ns % TACT_NS == 0:
        return time_ns
    return ((time_ns // TACT_NS) + 1) * TACT_NS


class RadarSystem:
    def __init__(self, num_stations: int):
        self.num_stations = num_stations
        self.state = GlobalState.IDLE

        self.pending_requests:   List[RadarRequest] = []
        self.active_requests:    List[RadarRequest] = []
        self.completed_requests: List[RadarRequest] = []
        self.lost_requests:      List[RadarRequest] = []

        self.max_emit = self.max_recv = self.max_proc = 0
        self.current_tact_end = 0

        self._primary_station = 0

    def add_request(self, req: RadarRequest):
        heapq.heappush(self.pending_requests, req)

    # ------------------------------------------------------------------
    def _purge_expired(self, current_time: int):
       
        pass  

    # ------------------------------------------------------------------
    def _pop_all(self, current_time: int) -> list:
    
        alive: List[RadarRequest] = []
        while self.pending_requests:
            cand = heapq.heappop(self.pending_requests)
            if current_time + cand.total_duration_ns() > cand.deadline_ns:
                self.lost_requests.append(cand)
            else:
                alive.append(cand)
        return alive

    # ------------------------------------------------------------------
    def _select_pair(
        self,
        alive: List[RadarRequest],
        current_time: int,
        remaining: int,
    ) -> tuple[Optional[RadarRequest], Optional[RadarRequest], set]:
        
        if not alive:
            return None, None, set()

        alive.sort()   # по убыванию приоритета, затем по дедлайну
        solo_ok = [(i, r) for i, r in enumerate(alive)
                   if r.total_duration_ns() <= remaining]
        pair_ok = [(i, r) for i, r in enumerate(alive)
                   if r.total_duration_ns() > remaining]

        if not solo_ok:
            return None, None, set()

        first_idx, first = solo_ok[0]
        used = {first_idx}

        best_second     = None
        best_second_idx = -1
        best_score      = float(remaining - first.total_duration_ns())

        candidates = solo_ok[1:] + pair_ok
        limit = min(len(candidates), MAX_PAIR_SEARCH)
        for i in range(limit):
            alive_idx, cand = candidates[i]
            joint = first.joint_duration_ns(cand)

            if joint > remaining:
                continue
            if current_time + joint > first.deadline_ns:
                continue
            if current_time + joint > cand.deadline_ns:
                continue

            inter_waste = remaining - joint
            mismatch = (
                abs(first.emission_duration_ns   - cand.emission_duration_ns)
              + abs(first.reception_duration_ns  - cand.reception_duration_ns)
              + abs(first.processing_duration_ns - cand.processing_duration_ns)
            )
            MISMATCH_WEIGHT = 0.3
            score = inter_waste + MISMATCH_WEIGHT * mismatch

            if score < best_score:
                best_score      = score
                best_second     = cand
                best_second_idx = alive_idx

        if best_second is not None:
            used.add(best_second_idx)

        return first, best_second, used

    def try_start_cycle(self, current_time: int, tact_end: int) -> Optional[Event]:
        
        if self.state != GlobalState.IDLE:
            return None

        remaining = tact_end - current_time
        if remaining <= 0:
            return None

        self.current_tact_end = tact_end
        self._purge_expired(current_time)  

        alive = self._pop_all(current_time)
        if not alive:
            return None

        first, second, used_indices = self._select_pair(alive, current_time, remaining)

        for i, req in enumerate(alive):
            if i not in used_indices:
                heapq.heappush(self.pending_requests, req)

        if first is None:
            return None

        selected = [first, second] if second is not None else [first]

        primary   = self._primary_station
        secondary = 1 - primary
        self._primary_station = secondary

        first.assigned_station  = primary
        first.actual_emit_start = current_time
        if second is not None:
            second.assigned_station  = secondary
            second.actual_emit_start = current_time

        self.max_emit = max(r.emission_duration_ns   for r in selected)
        self.max_recv = max(r.reception_duration_ns  for r in selected)
        self.max_proc = max(r.processing_duration_ns for r in selected)
        self.active_requests = selected

        if self.max_emit > 0:
            self.state          = GlobalState.TRANSMIT
            self.phase_end_time = current_time + self.max_emit
            return Event(self.phase_end_time, "PHASE_END", {"phase": "TRANSMIT"})
        else:
            return self._start_receive_phase(current_time)

    # ------------------------------------------------------------------
    def _start_receive_phase(self, current_time: int) -> Event:
        self.state          = GlobalState.RECEIVE
        self.phase_end_time = current_time + self.max_recv
        for req in self.active_requests:
            req.actual_recv_start = current_time
        return Event(self.phase_end_time, "PHASE_END", {"phase": "RECEIVE"})

    def _start_process_phase(self, current_time: int) -> Event:
        self.state          = GlobalState.PROCESS
        self.phase_end_time = current_time + self.max_proc
        for req in self.active_requests:
            req.actual_proc_start = current_time
        return Event(self.phase_end_time, "PHASE_END", {"phase": "PROCESS"})

    def finish_cycle(self, current_time: int):
        for req in self.active_requests:
            if req.actual_emit_start >= 0:
                req.actual_emit_end = req.actual_emit_start + req.emission_duration_ns
            if req.actual_recv_start >= 0:
                req.actual_recv_end = req.actual_recv_start + req.reception_duration_ns
            if req.actual_proc_start >= 0:
                req.actual_proc_end = req.actual_proc_start + req.processing_duration_ns

            ok = (req.actual_proc_end > 0
                  and req.actual_proc_end <= req.deadline_ns)
            (self.completed_requests if ok else self.lost_requests).append(req)

        self.active_requests = []
        self.state = GlobalState.IDLE

    def handle_phase_end(self, current_time: int, phase: str) -> Optional[Event]:
        if phase == "TRANSMIT":
            return self._start_receive_phase(current_time)
        elif phase == "RECEIVE":
            return self._start_process_phase(current_time)
        elif phase == "PROCESS":
            self.finish_cycle(current_time)
            return None
        return None


def plot_all_schedule(requests_to_plot: List[RadarRequest], plot_limit: int = 200):
    COLOR_EMIT = "#ff6b6b"   # мягкий красный
    COLOR_RECV = "#4ecdc4"   # бирюзовый
    COLOR_PROC = "#ffe66d"   # жёлтый

    reqs = sorted(requests_to_plot, key=lambda r: r.actual_emit_start)[:plot_limit]
    if not reqs:
        print("Нет заявок для отображения.")
        return

    fig = make_subplots(
        rows=STATIONS, cols=1, shared_xaxes=True,
        subplot_titles=[f"Станция {i+1}" for i in range(STATIONS)],
        vertical_spacing=0.1,
    )

    for color, name in [(COLOR_EMIT, "Излучение"),
                        (COLOR_RECV, "Приём"),
                        (COLOR_PROC, "Обработка")]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines",
                                  line=dict(color=color), name=name,
                                  showlegend=True), row=1, col=1)

    min_t = min(r.actual_emit_start for r in reqs)
    max_t = max(r.actual_proc_end   for r in reqs)
    for t in range(min_t // TACT_NS, max_t // TACT_NS + 2):
        fig.add_vline(x=t * TACT_NS / 1e6, line_width=1,
                      line_dash="dot", line_color="gray", row="all", col=1)

    def add_bar(req, start, end, color, label):
        if end <= start:
            return
        hover = (f"ID:{req.req_id} tipz:{req.tipz} prio:{req.priority}<br>"
                 f"{label}: {start/1e6:.3f}–{end/1e6:.3f} мс  "
                 f"({(end-start)/1e6:.3f} мс)")
        s = req.assigned_station
        fig.add_trace(go.Scatter(
            x=[start/1e6, end/1e6, end/1e6, start/1e6, start/1e6],
            y=[s+0.1, s+0.1, s+0.9, s+0.9, s+0.1],
            fill="toself", mode="lines", line=dict(color=color),
            showlegend=False, hoverinfo="text", text=hover,
        ), row=s + 1, col=1)

    for req in reqs:
        if not (0 <= req.assigned_station < STATIONS):
            continue
        add_bar(req, req.actual_emit_start, req.actual_emit_end, COLOR_EMIT, "Излучение")
        add_bar(req, req.actual_recv_start, req.actual_recv_end, COLOR_RECV, "Приём")
        add_bar(req, req.actual_proc_start, req.actual_proc_end, COLOR_PROC, "Обработка")

    for i in range(STATIONS):
        fig.update_yaxes(range=[i, i+1], tickvals=[i+0.5],
                         ticktext=[f"Ст.{i+1}"], row=i+1, col=1)
    fig.update_xaxes(title_text="Время (мс)", row=STATIONS, col=1)
    fig.update_layout(
        title=f"Диаграмма Ганта (первые {plot_limit} заявок)",
        height=400 * STATIONS,
        xaxis=dict(rangeslider=dict(visible=True)),
        hovermode="closest",
    )
    fig.show()


def plot_tact_analysis(requests: List[RadarRequest],
                        tact_ns: int, max_requests: int = 500):
    valid = sorted(
        [r for r in requests if r.actual_emit_start >= 0 and r.actual_proc_end > 0],
        key=lambda r: r.actual_emit_start
    )[:max_requests]
    if not valid:
        print("Нет данных для анализа тактов.")
        return

    min_t = min(r.actual_emit_start for r in valid)
    max_t = max(r.actual_proc_end   for r in valid)
    min_tact = min_t // tact_ns
    max_tact = (max_t + tact_ns - 1) // tact_ns

    busy_segs = []
    proc_segs = []
    for r in valid:
        for s, e in [(r.actual_emit_start, r.actual_emit_end),
                     (r.actual_recv_start, r.actual_recv_end),
                     (r.actual_proc_start, r.actual_proc_end)]:
            if s >= 0 and e > s:
                busy_segs.append((s, e))
        if r.actual_proc_start >= 0 and r.actual_proc_end > r.actual_proc_start:
            proc_segs.append((r.actual_proc_start, r.actual_proc_end))

    def merge(segs):
        if not segs:
            return []
        segs = sorted(segs)
        out = [segs[0]]
        for s, e in segs[1:]:
            if s <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], e))
            else:
                out.append((s, e))
        return out

    def overlap_sum(segs, ts, te):
        total = 0
        for s, e in segs:
            if e > ts and s < te:
                total += min(e, te) - max(s, ts)
        return total

    busy_merged = merge(busy_segs)

    tact_ids, fill_pcts, idle_ms, proc_ms = [], [], [], []
    for t in range(min_tact, max_tact + 1):
        ts, te = t * tact_ns, (t + 1) * tact_ns
        busy = overlap_sum(busy_merged, ts, te)
        proc = overlap_sum(proc_segs,   ts, te)
        idle = tact_ns - busy
        tact_ids.append(t)
        fill_pcts.append(100 * busy / tact_ns)
        idle_ms.append(idle / 1e6)
        proc_ms.append(proc / 1e6)

    avg_fill = sum(fill_pcts) / len(fill_pcts) if fill_pcts else 0

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        subplot_titles=(
            f"Заполненность такта (%) — среднее {avg_fill:.1f}%",
            "Пустое время в такте (мс)",
            "Время обработки в такте (мс)",
        ),
        vertical_spacing=0.12,
    )
    colors = ["#2ecc71" if p >= 80 else "#f39c12" if p >= 50 else "#e74c3c"
              for p in fill_pcts]

    fig.add_trace(go.Bar(x=tact_ids, y=fill_pcts, name="Заполненность",
                          marker_color=colors), row=1, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="green",
                  annotation_text="80%", row=1, col=1)
    fig.add_hline(y=100, line_dash="dash", line_color="gray",
                  annotation_text="100%", row=1, col=1)
    fig.add_trace(go.Bar(x=tact_ids, y=idle_ms, name="Пустое время",
                          marker_color="orange"), row=2, col=1)
    fig.add_trace(go.Bar(x=tact_ids, y=proc_ms, name="Обработка",
                          marker_color="steelblue"), row=3, col=1)

    fig.update_xaxes(title_text="Номер такта", row=3, col=1)
    fig.update_yaxes(title_text="%",  range=[0, 105], row=1, col=1)
    fig.update_yaxes(title_text="мс", row=2, col=1)
    fig.update_yaxes(title_text="мс", row=3, col=1)
    fig.update_layout(
        title=(f"Анализ тактов | {len(valid)} заявок | "
               f"Среднее заполнение: {avg_fill:.1f}%"),
        height=800, showlegend=False,
    )
    fig.show()


PRIO_HIGH_THRESHOLD = 8000
PRIO_LOW_THRESHOLD  = 8000
TIPZ_NAMES = {71: "Поиск", 75: "Захват", 76: "Сопровождение", 141: "Помехи"}


def _classify(req: "RadarRequest"):
    if req.priority >= PRIO_HIGH_THRESHOLD:
        tier = "high"
    elif req.priority < PRIO_LOW_THRESHOLD:
        tier = "low"
    else:
        tier = "mid"
    return tier, TIPZ_NAMES.get(req.tipz, f"tipz{req.tipz}")


def _segs_to_tact_ns(segs_sorted, tact_ns, min_tact, max_tact):
    n = max_tact - min_tact + 1
    result = [0] * n
    if not segs_sorted:
        return result
    ns = len(segs_sorted)
    seg_i = 0
    for ti in range(n):
        ts = (min_tact + ti) * tact_ns
        te = ts + tact_ns
        while seg_i < ns and segs_sorted[seg_i][1] <= ts:
            seg_i += 1
        j, total = seg_i, 0
        while j < ns and segs_sorted[j][0] < te:
            s, e = segs_sorted[j]
            total += min(e, te) - max(s, ts)
            j += 1
        result[ti] = total
    return result


def compute_tact_stats(completed, lost, tact_ns):
    from collections import defaultdict

    all_reqs = completed + lost
    if not all_reqs:
        return {}

    min_tact = min(r.tgel_ns for r in all_reqs) // tact_ns
    max_tact = max(r.tgel_ns for r in all_reqs) // tact_ns

    def merge(segs):
        if not segs:
            return []
        segs = sorted(segs)
        out = [list(segs[0])]
        for s, e in segs[1:]:
            if s <= out[-1][1]:
                out[-1][1] = max(out[-1][1], e)
            else:
                out.append([s, e])
        return [tuple(x) for x in out]

    busy_raw, proc_raw = [], []
    for r in completed:
        for s, e in [(r.actual_emit_start, r.actual_emit_end),
                     (r.actual_recv_start, r.actual_recv_end),
                     (r.actual_proc_start, r.actual_proc_end)]:
            if s >= 0 and e > s:
                busy_raw.append((s, e))
        if r.actual_proc_start >= 0 and r.actual_proc_end > r.actual_proc_start:
            proc_raw.append((r.actual_proc_start, r.actual_proc_end))

    busy_merged = merge(busy_raw)
    proc_merged = merge(proc_raw)

    busy_arr = _segs_to_tact_ns(busy_merged, tact_ns, min_tact, max_tact)
    proc_arr = _segs_to_tact_ns(proc_merged, tact_ns, min_tact, max_tact)

    tact_completed = defaultdict(list)
    tact_lost      = defaultdict(list)
    for r in completed:
        tact_completed[r.tgel_ns // tact_ns].append(r)
    for r in lost:
        tact_lost[r.tgel_ns // tact_ns].append(r)

    results = {}
    n = max_tact - min_tact + 1
    for i in range(n):
        tid     = min_tact + i
        busy_ns = busy_arr[i]
        proc_ns = proc_arr[i]
        idle_ns = tact_ns - busy_ns

        done    = tact_completed.get(tid, [])
        dropped = tact_lost.get(tid, [])

        def split(reqs):
            from collections import defaultdict
            high, low, by_tipz = [], [], defaultdict(list)
            for r in reqs:
                tier, tname = _classify(r)
                if tier == "high":
                    high.append(r)
                elif tier == "low":
                    low.append(r)
                by_tipz[tname].append(r)
            return high, low, dict(by_tipz)

        dh, dl, db = split(done)
        rh, rl, rb = split(dropped)
        ah = len(dh) + len(rh)
        al = len(dl) + len(rl)

        results[tid] = {
            "idle_ns":         idle_ns,
            "busy_ns":         busy_ns,
            "proc_ns":         proc_ns,
            "idle_pct":        100 * idle_ns / tact_ns,
            "busy_pct":        100 * busy_ns / tact_ns,
            "high_arrived":    ah,
            "high_done":       len(dh),
            "high_dropped":    len(rh),
            "high_ratio":      len(dh) / ah if ah else None,
            "low_arrived":     al,
            "low_done":        len(dl),
            "low_dropped":     len(rl),
            "low_ratio":       len(dl) / al if al else None,
            "by_tipz_done":    db,
            "by_tipz_dropped": rb,
        }

    return results


def plot_priority_ratio(stats: dict, tact_ns: int, interval: int = 200):
    from collections import defaultdict

    all_ids = sorted(stats.keys())
    if not all_ids:
        return

    labels, h_pcts, l_pcts, ratios, idle_pcts = [], [], [], [], []

    i = 0
    while i < len(all_ids):
        chunk = all_ids[i:i+interval]
        cs    = [stats[t] for t in chunk]

        h_done = sum(s["high_done"]    for s in cs)
        h_drop = sum(s["high_dropped"] for s in cs)
        l_done = sum(s["low_done"]     for s in cs)
        l_drop = sum(s["low_dropped"]  for s in cs)

        h_total = h_done + h_drop
        l_total = l_done + l_drop
        hp      = 100 * h_done / h_total if h_total else None
        lp      = 100 * l_done / l_total if l_total else None
        ratio   = (hp / lp) if (hp is not None and lp and lp > 0) else None

        labels.append(f"{chunk[0]}")
        h_pcts.append(hp)
        l_pcts.append(lp)
        ratios.append(ratio)
        idle_pcts.append(sum(s["idle_pct"] for s in cs) / len(cs))
        i += interval

    ratio_colors = []
    for r in ratios:
        if r is None:     ratio_colors.append("#aaaaaa")
        elif r >= 1.05:   ratio_colors.append("#2ecc71")
        elif r >= 0.95:   ratio_colors.append("#f39c12")
        else:             ratio_colors.append("#e74c3c")

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        subplot_titles=(
            "% выполнения: Высокий (prio≥8000) vs Низкий (prio<8000)",
            "Отношение H% / L%  (>1 = высокий обслуживается лучше)",
            "Пустое время такта (%)",
        ),
        vertical_spacing=0.10,
    )

    fig.add_trace(go.Bar(
        x=labels, y=h_pcts, name="Высокий prio (≥8000)",
        marker_color="#3498db",
        hovertemplate="Такт %{x}<br>H выполнено: %{y:.1f}%<extra></extra>",
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=labels, y=l_pcts, name="Низкий prio (<8000)",
        marker_color="#e67e22",
        hovertemplate="Такт %{x}<br>L выполнено: %{y:.1f}%<extra></extra>",
    ), row=1, col=1)
    fig.add_hline(y=100, line_dash="dot", line_color="gray", row=1, col=1)

    fig.add_trace(go.Bar(
        x=labels, y=ratios, name="H% / L%",
        marker_color=ratio_colors,
        hovertemplate="Такт %{x}<br>H%/L% = %{y:.3f}<extra></extra>",
    ), row=2, col=1)
    fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                  annotation_text="1.0 (равное обслуживание)",
                  annotation_position="top right", row=2, col=1)

    idle_colors = ["#2ecc71" if p < 20 else "#f39c12" if p < 60 else "#e74c3c"
                   for p in idle_pcts]
    fig.add_trace(go.Bar(
        x=labels, y=idle_pcts, name="Idle %",
        marker_color=idle_colors,
        hovertemplate="Такт %{x}<br>Idle: %{y:.1f}%<extra></extra>",
    ), row=3, col=1)

    fig.update_xaxes(title_text=f"Номер такта (группы по {interval})", row=3, col=1)
    fig.update_yaxes(title_text="%", range=[0, 105], row=1, col=1)
    fig.update_yaxes(title_text="H% / L%", row=2, col=1)
    fig.update_yaxes(title_text="Idle %", range=[0, 105], row=3, col=1)
    fig.update_layout(
        title="Анализ приоритетов по тактам: отношение выполнения H/L",
        height=800, barmode="group", hovermode="x unified",
        legend=dict(orientation="h", y=1.05),
    )
    fig.show()


def print_summary_stats(
    completed,
    lost,
    tact_ns,
    interval=100,
):
    stats = compute_tact_stats(completed, lost, tact_ns)

    if not stats:
        print("Нет данных для статистики.")
        return

    tact_ms = tact_ns / 1e6
    all_ids = sorted(stats.keys())

    total_tacts = len(all_ids)
    total_idle = sum(s["idle_ns"] for s in stats.values())
    total_busy = sum(s["busy_ns"] for s in stats.values())
    total_proc = sum(s["proc_ns"] for s in stats.values())
    total_time = total_tacts * tact_ns

    print()
    print("=" * 72)
    print("ДЕТАЛЬНАЯ СТАТИСТИКА")
    print("=" * 72)

    print(f"Тактов проанализировано : {total_tacts}")
    print(f"Суммарное время         : {total_time / 1e9:.3f} с")

    print()
    print("ИСПОЛЬЗОВАНИЕ ВРЕМЕНИ")
    print("-" * 72)

    print(
        f"Занятое время           : "
        f"{total_busy / 1e9:.3f} с "
        f"({100 * total_busy / total_time:.1f}%)"
    )

    print(
        f"Пустое время (idle)     : "
        f"{total_idle / 1e9:.3f} с "
        f"({100 * total_idle / total_time:.1f}%)"
    )

    print(
        f"Из них на обработку     : "
        f"{total_proc / 1e9:.3f} с "
        f"({100 * total_proc / total_time:.1f}%)"
    )

    print(
        f"Среднее idle на такт    : "
        f"{total_idle / total_tacts / 1e6:.2f} мс "
        f"(из {tact_ms:.2f} мс)"
    )

    idle_pcts = [s["idle_pct"] for s in stats.values()]

    n_good = sum(1 for p in idle_pcts if p < 20)
    n_mid = sum(1 for p in idle_pcts if 20 <= p < 60)
    n_bad = sum(1 for p in idle_pcts if p >= 60)

    print()
    print("РАСПРЕДЕЛЕНИЕ ЗАПОЛНЕННОСТИ ТАКТОВ")
    print("-" * 72)

    print(
        f"Хорошо (idle < 20%) : "
        f"{n_good} тактов ({100 * n_good / total_tacts:.1f}%)"
    )

    print(
        f"Средне (20-60%)     : "
        f"{n_mid} тактов ({100 * n_mid / total_tacts:.1f}%)"
    )

    print(
        f"Плохо (idle >= 60%) : "
        f"{n_bad} тактов ({100 * n_bad / total_tacts:.1f}%)"
    )

    def agg(key_arr, key_done, key_drop):
        arr = sum(s[key_arr] for s in stats.values())
        done = sum(s[key_done] for s in stats.values())
        drop = sum(s[key_drop] for s in stats.values())

        pct = 100 * done / arr if arr else 0

        return arr, done, drop, pct

    ha, hd, hl, hp = agg(
        "high_arrived",
        "high_done",
        "high_dropped"
    )

    la, ld, ll, lp = agg(
        "low_arrived",
        "low_done",
        "low_dropped"
    )

    print()
    print("ПРИОРИТЕТЫ")
    print("-" * 72)

    print(
        f"{'Группа':<28}"
        f"{'Поступило':>10}"
        f"{'Выполнено':>10}"
        f"{'Потеряно':>10}"
        f"{'% выполн':>10}"
    )

    print("-" * 72)

    print(
        f"{'Высокий (prio >= 8000)':28}"
        f"{ha:10d}"
        f"{hd:10d}"
        f"{hl:10d}"
        f"{hp:9.1f}%"
    )

    print(
        f"{'Низкий (prio < 8000)':28}"
        f"{la:10d}"
        f"{ld:10d}"
        f"{ll:10d}"
        f"{lp:9.1f}%"
    )

    from collections import defaultdict

    tipz_done = defaultdict(int)
    tipz_dropped = defaultdict(int)

    for s in stats.values():

        for k, v in s["by_tipz_done"].items():
            tipz_done[k] += len(v)

        for k, v in s["by_tipz_dropped"].items():
            tipz_dropped[k] += len(v)

    all_tipz = sorted(
        set(
            list(tipz_done.keys())
            + list(tipz_dropped.keys())
        )
    )

    print()
    print("ПО ТИПАМ ЗАЯВОК")
    print("-" * 72)

    print(
        f"{'Тип':<20}"
        f"{'Выполнено':>10}"
        f"{'Потеряно':>10}"
        f"{'Всего':>10}"
        f"{'% выполн':>10}"
    )

    print("-" * 72)

    for tipz in all_tipz:

        d = tipz_done.get(tipz, 0)
        dr = tipz_dropped.get(tipz, 0)

        total = d + dr

        pct = 100 * d / total if total else 0

        print(
            f"{tipz:<20}"
            f"{d:10d}"
            f"{dr:10d}"
            f"{total:10d}"
            f"{pct:9.1f}%"
        )

    print("=" * 72)

    plot_priority_ratio(
        stats,
        tact_ns,
        interval
    )


def plot_system_load(requests: List[RadarRequest], tact_ns: int):
    load = {}

    for r in requests:
        tact = r.tgel_ns // tact_ns
        load[tact] = load.get(tact, 0) + r.total_duration_ns()

    tacts = sorted(load.keys())
    values = [100 * load[t] / tact_ns for t in tacts]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=tacts,
        y=values,
        mode="lines+markers",
        line=dict(color="#00ffcc", width=2),
        name="Загрузка"
    ))

    fig.update_layout(
        title="Загрузка РЛС по тактам (%)",
        xaxis_title="Такт",
        yaxis_title="%",
        template="plotly_dark"
    )

    fig.show()


def plot_losses_timeline(lost: List[RadarRequest], tact_ns: int):
    loss = {}

    for r in lost:
        tact = r.tgel_ns // tact_ns
        loss[tact] = loss.get(tact, 0) + 1

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=list(loss.keys()),
        y=list(loss.values()),
        marker_color="#ff3b3b",
        name="Потери"
    ))

    fig.update_layout(
        title="Потери заявок по тактам",
        xaxis_title="Такт",
        yaxis_title="Количество",
        template="plotly_dark"
    )

    fig.show()


def plot_priority_distribution(all_requests: List[RadarRequest]):
    prios = [r.priority for r in all_requests]

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=prios,
        nbinsx=30,
        marker_color="#a29bfe",
        name="Приоритеты"
    ))

    fig.update_layout(
        title="Распределение приоритетов заявок",
        xaxis_title="Приоритет",
        yaxis_title="Количество",
        template="plotly_dark"
    )

    fig.show()
def run_simulation_model():
     
    file_paths = [
        r"C:\games\log\40179\comfu_request1.log",
        r"C:\games\log\40179\comfu_request2.log",
        r"C:\games\log\40179\comfu_request3.log",
    ]

    all_requests_raw = []

    for path in file_paths:
        reqs = parse_log(path)
        all_requests_raw.extend(reqs)

    if not all_requests_raw:
        return None

    system = RadarSystem(STATIONS)

    event_queue = []

    for req in all_requests_raw:
        heapq.heappush(
            event_queue,
            Event(req.tgel_ns, "ARRIVAL", req)
        )

    scheduled_starts = set()

    def schedule_start(t):
        if t not in scheduled_starts:
            scheduled_starts.add(t)
            heapq.heappush(
                event_queue,
                Event(t, "START_CYCLE")
            )

    def maybe_schedule(current_time):
        if system.state == GlobalState.IDLE:
            schedule_start(
                next_tact_start(current_time)
            )

    while (
        event_queue
        or system.state != GlobalState.IDLE
        or system.pending_requests
    ):

        if not event_queue:
            break

        ev = heapq.heappop(event_queue)

        t = ev.time_ns

        if ev.etype == "ARRIVAL":

            system.add_request(ev.data)

            maybe_schedule(t)

        elif ev.etype == "START_CYCLE":

            scheduled_starts.discard(t)

            tact_end = t + TACT_NS

            new_ev = system.try_start_cycle(
                t,
                tact_end
            )

            if new_ev:

                heapq.heappush(
                    event_queue,
                    new_ev
                )

            elif system.pending_requests:

                schedule_start(
                    t + TACT_NS
                )

        elif ev.etype == "PHASE_END":

            new_ev = system.handle_phase_end(
                t,
                ev.data["phase"]
            )

            if new_ev:

                heapq.heappush(
                    event_queue,
                    new_ev
                )

    total = len(all_requests_raw)

    completed = system.completed_requests

    lost = system.lost_requests

    return {
        "total": total,
        "completed": completed,
        "lost": lost,
        "loss_percent":
            round(
                len(lost) /
                total *
                100,
                2
            )
    }
def main():
    print("Загрузка логов...")

    file_paths = [
    r"C:\games\log\40179\comfu_request1.log",
    r"C:\games\log\40179\comfu_request2.log",
    r"C:\games\log\40179\comfu_request3.log",
]

    all_requests_raw = []
    for i, path in enumerate(file_paths, start=1):
        reqs = parse_log(path)
        print(f"  Файл {i}: {path} — {len(reqs)} заявок")
        all_requests_raw.extend(reqs)

    if not all_requests_raw:
        print("Нет заявок для обработки.")
        return

    system = RadarSystem(STATIONS)
    event_queue = []

    for req in all_requests_raw:
        heapq.heappush(event_queue, Event(req.tgel_ns, "ARRIVAL", req))

    scheduled_starts: set = set()

    def schedule_start(t: int):
        if t not in scheduled_starts:
            scheduled_starts.add(t)
            heapq.heappush(event_queue, Event(t, "START_CYCLE"))

    def maybe_schedule(current_time: int):
        if system.state == GlobalState.IDLE:
            schedule_start(next_tact_start(current_time))

    print("\nЗапуск симуляции...\n")

    while event_queue or system.state != GlobalState.IDLE or system.pending_requests:
        if not event_queue:
            break

        ev = heapq.heappop(event_queue)
        t  = ev.time_ns

        if ev.etype == "ARRIVAL":
            system.add_request(ev.data)
            maybe_schedule(t)

        elif ev.etype == "START_CYCLE":
            scheduled_starts.discard(t)
            tact_end = t + TACT_NS
            new_ev = system.try_start_cycle(t, tact_end)
            if new_ev:
                heapq.heappush(event_queue, new_ev)
            elif system.pending_requests:
                schedule_start(t + TACT_NS)
            else:
                if event_queue:
                    next_ev = event_queue[0]
                    if next_ev.etype == "ARRIVAL":
                        next_tact = next_tact_start(next_ev.time_ns)
                        schedule_start(next_tact)

        elif ev.etype == "PHASE_END":
            new_ev = system.handle_phase_end(t, ev.data["phase"])
            if new_ev:
                heapq.heappush(event_queue, new_ev)
            else:
                tact_end = system.current_tact_end
                if t < tact_end and system.pending_requests:
                    cont = system.try_start_cycle(t, tact_end)
                    if cont:
                        heapq.heappush(event_queue, cont)
                    else:
                        maybe_schedule(t)
                else:
                    maybe_schedule(t)

    print("Симуляция завершена.\n")

    if system.lost_requests:
        print("\n ПОТЕРЯВШИЕСЯ ЗАЯВКИ")
        # Сортируем по времени поступления для удобства
        lost_sorted = sorted(system.lost_requests, key=lambda x: x.tgel_ns)

        print(f" Всего потеряно: {len(lost_sorted)} заявок\n")

        # Группировка по причинам потери
        expired_by_deadline = 0
        no_slot_available = 0

        for req in lost_sorted:
            if req.actual_emit_start == -1:  # Не начали выполняться
                no_slot_available += 1
            else:  # Начали, но не уложились в дедлайн
                expired_by_deadline += 1

        print(f" Не влезли в расписание: {no_slot_available}")
        print(f" Не уложились в дедлайн: {expired_by_deadline}")

        print("\n Детальная информация (первые 20):")
        print("-" * 80)
        print(f"{'ID':>6} {'Тип':>6} {'Приоритет':>10} {'Время поступления':>18} {'Дедлайн':>12} {'Длит.':>8}")
        print("-" * 80)

        for req in lost_sorted[500:700]:  # Показываем первые 20
            tgel_tact = req.tgel_ns // TACT_NS
            deadline_tact = req.deadline_ns // TACT_NS
            duration_ms = req.total_duration_ns() / 1e6

            print(f"{req.req_id:6d} {req.tipz:6d} {req.priority:10d} "
                  f"Такт {tgel_tact:4d} ({req.tgel_ns/1e6:8.2f}ms) "
                  f"Такт {deadline_tact:4d} {duration_ms:8.2f}ms")

        if len(lost_sorted) > 20:
            print(f"... и еще {len(lost_sorted) - 20} заявок")


        total     = len(all_requests_raw)
        completed = system.completed_requests
        lost      = system.lost_requests

    print("ИТОГИ")
    print(f" Всего поступило : {total}")
    print(f" Выполнено в срок: {len(completed)}")
    print(f" Потеряно: {len(lost)}")
    if total:
        print(f" Процент потерь: {len(lost)/total*100:.2f}%")

    print_summary_stats(completed, lost, TACT_NS, interval=200)

    plot_limit = 500
    print(f"\n График Ганта (первые {plot_limit})...")
    plot_all_schedule(completed, plot_limit)

    print(f"\n Анализ тактов (первые {plot_limit})...")
    plot_tact_analysis(completed, TACT_NS, plot_limit)
    print("\n Дополнительная аналитика...")

    plot_system_load(completed, TACT_NS)
    plot_losses_timeline(lost, TACT_NS)
    plot_priority_distribution(all_requests_raw)

if __name__ == "__main__":
    main()