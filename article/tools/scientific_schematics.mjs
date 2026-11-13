// Publication schematics. Labels occupy reserved areas outside connector routes.
const esc = s => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;');
const t = (x,y,s,size=30,bold=false,anchor='middle') => `<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="Arial, sans-serif" font-size="${size}" font-weight="${bold?700:400}" fill="#111">${esc(s)}</text>`;
const box = (x,y,w,h) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="white" stroke="#222" stroke-width="2.5"/>`;
const line = (d,dashed=false,both=false) => `<path d="${d}" fill="none" stroke="#333" stroke-width="3" ${dashed?'stroke-dasharray="10 7"':''} marker-end="url(#arrow)" ${both?'marker-start="url(#arrow)"':''}/>`;
const wrap = (h,body) => `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="${h}" viewBox="0 0 1600 ${h}"><rect width="1600" height="${h}" fill="white"/><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="#333"/></marker></defs>${body.join('\n')}</svg>`;

export function architecture(lang) {
  const ru=lang==='ru', b=[];
  b.push(t(800,65,ru?'Схема испытательного стенда':'Experimental testbed',36,true));
  b.push(t(800,110,ru?'Одна аппаратная пара в каждом цикле':'One hardware pair per cycle',28));
  b.push(box(100,220,440,160),box(1060,220,440,160));
  b.push(t(320,280,ru?'Отправитель':'Sender',34,true),t(1280,280,ru?'Приёмник':'Receiver',34,true));
  for(const x of [320,1280]) b.push(t(x,330,'ESP8266 / ESP32 / ESP32-S3',26));
  b.push(t(800,195,'ESP-NOW',30,true),t(800,245,'probe',28));
  b.push(line('M555 270 H1045'),line('M1045 345 H555'),t(800,320,ru?'Прикладной ACK':'Application ACK',28));
  b.push(box(540,500,520,140),t(800,550,ru?'Точка доступа 2,4 ГГц':'2.4 GHz access point',32,true),t(800,600,ru?'Lab-2G · канал 6':'Lab-2G · channel 6',28));
  b.push(line('M430 395 V570 H525',true,true),line('M1170 395 V570 H1075',true,true));
  b.push(t(800,425,'Wi-Fi / UDP',30,true),t(800,465,'probe: broadcast · ACK: unicast',27));
  b.push(box(540,770,520,140),t(800,825,ru?'Компьютер управления':'Control computer',32,true),t(800,870,ru?'Python GUI · журнал JSONL':'Python GUI · JSONL log',28));
  b.push(line('M190 395 V840 H525',false,true),line('M1410 395 V840 H1075',false,true));
  b.push(t(800,705,'USB Serial',30,true),t(800,745,ru?'Команды и телеметрия':'Commands and telemetry',28));
  b.push(t(800,965,'ESP8266–ESP32   ·   ESP8266–ESP32-S3   ·   ESP32–ESP32-S3',26));
  return wrap(1000,b);
}

export function stateMachine(lang) {
  const ru=lang==='ru', b=[];
  b.push(t(800,55,ru?'Автомат выбора транспорта':'Transport selection state machine',36,true));
  b.push(t(800,104,ru?'Запуск':'Start',28),line('M800 115 V150'));
  b.push(box(530,160,540,210),t(800,207,'ESP-NOW',36,true));
  b.push(t(800,250,ru?'Основной транспорт · probe 470 мс':'Primary transport · probe 470 ms',28));
  b.push(t(800,298,ru?'При каждом входе: стабилизация':'On every entry: stabilization',28));
  b.push(t(800,342,ru?'3 окна без переключения':'3 windows without switching',28));
  b.push(box(530,610,540,150),t(800,658,'UDP',36,true));
  b.push(t(800,703,ru?'Резерв через точку доступа':'Backup through access point',28));
  b.push(t(800,744,ru?'Проверка ESP-NOW каждые 940 мс':'ESP-NOW probes every 940 ms',27));
  b.push(line('M1080 265 H1170 V685 H1080'));
  b.push(line('M520 685 H430 V265 H520'));
  const left=ru?['ACK ESP-NOW ≥ 80 %','3 окна подряд','по 5 с']:['ESP-NOW ACK ≥ 80%','3 consecutive windows','of 5 s each'];
  const right=ru?['Потери ESP-NOW ≥ 30 %','2 окна подряд по 5 с','Wi-Fi подключён','UDP запущен']:['ESP-NOW loss ≥ 30%','2 consecutive 5 s windows','Wi-Fi connected','UDP active'];
  left.forEach((s,i)=>b.push(t(390,440+i*43,s,27,i===0,'end')));
  right.forEach((s,i)=>b.push(t(1210,418+i*43,s,25,i===0,'start')));
  b.push(t(800,840,ru?'Пороговые условия проверяются при достаточном числе probe в окне.':'Thresholds are evaluated only with sufficient probes in the window.',27));
  b.push(t(800,888,ru?'Решения основаны на прикладных ACK ESP-NOW.':'Decisions use ESP-NOW application acknowledgements.',28));
  b.push(t(800,936,ru?'Параметры показаны для исследованной конфигурации.':'Parameters shown correspond to the tested configuration.',27));
  return wrap(980,b);
}
