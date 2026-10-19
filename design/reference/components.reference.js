/* @ds-bundle: {"format":4,"namespace":"STA","components":[{"name":"Backdrop"},{"name":"Shell"},{"name":"TopNav"},{"name":"Glass"},{"name":"Button"},{"name":"Badge"},{"name":"Segmented"},{"name":"Field"},{"name":"SearchPill"},{"name":"StatTile"},{"name":"FlightPass"},{"name":"Board"},{"name":"Meter"},{"name":"SeatMap"},{"name":"Dialog"},{"name":"ChatFab"},{"name":"Icon"}]} */
(function () {
  var React = window.React;
  var h = React.createElement;
  var useState = React.useState;

  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) { if (arguments[i]) out.push(arguments[i]); }
    return out.join(' ');
  }
  function rest(props, omit) {
    var o = {};
    for (var k in props) { if (Object.prototype.hasOwnProperty.call(props, k) && omit.indexOf(k) < 0) o[k] = props[k]; }
    return o;
  }

  /* ---------------- Icon ---------------- */
  var PATHS = {
    search: ['M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z', 'M20 20l-4.6-4.6'],
    plane: ['M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z'],
    calendar: ['M5.5 5h13a2 2 0 0 1 2 2v11.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z', 'M3.5 10h17', 'M8 3v4', 'M16 3v4'],
    wallet: ['M4 7.5A2.5 2.5 0 0 1 6.5 5H18v2.5', 'M6 7.5h12.5a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2.5 2.5 0 0 1-2.5-2.5V7.5', 'M16 14.5h.01'],
    ticket: ['M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2.5a2.5 2.5 0 0 0 0 5V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2.5a2.5 2.5 0 0 0 0-5z', 'M14.5 5.5v2', 'M14.5 11v2', 'M14.5 16.5v2'],
    message: ['M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 3.5V17H6.5A2.5 2.5 0 0 1 4 14.5z'],
    user: ['M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z', 'M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5'],
    cart: ['M3 4h2.5l2.2 10.5a1.5 1.5 0 0 0 1.5 1.2h7.6a1.5 1.5 0 0 0 1.5-1.1L20 8H6.4', 'M10 20h.01', 'M17 20h.01'],
    'chevron-down': ['M6 9l6 6 6-6'],
    'chevron-right': ['M9 6l6 6-6 6'],
    info: ['M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17z', 'M12 11v5', 'M12 7.8v.01'],
    x: ['M6 6l12 12', 'M18 6L6 18'],
    check: ['M5 12.5l4.5 4.5L19 7.5'],
    'arrow-up': ['M12 19V5', 'M6 11l6-6 6 6'],
    'arrow-down': ['M12 5v14', 'M6 13l6 6 6-6'],
    'arrow-right': ['M5 12h14', 'M13 6l6 6-6 6'],
    sliders: ['M4 7h9', 'M19 7h1', 'M4 17h2', 'M12 17h8', 'M16 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', 'M9 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z'],
    bell: ['M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z', 'M10 20.5h4'],
    plus: ['M12 5v14', 'M5 12h14'],
    alert: ['M12 4l9 16H3z', 'M12 10v4', 'M12 17v.01'],
    news: ['M6 4.5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2z', 'M8 9h8', 'M8 12.5h8', 'M8 16h5'],
    card: ['M5 6h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z', 'M3 10h18', 'M7 14.5h4'],
    tag: ['M3.5 12.5V5A1.5 1.5 0 0 1 5 3.5h7.5l8 8-9 9z', 'M8 8h.01'],
    list: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4.5 6h.01', 'M4.5 12h.01', 'M4.5 18h.01'],
    'check-circle': ['M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17z', 'M8.5 12.5l2.5 2.5 4.5-5']
  };
  function Icon(props) {
    var d = PATHS[props.name] || PATHS.info;
    return h('svg', { className: cx('sta-icon', props.size && 'sta-icon--' + props.size, props.className), viewBox: '0 0 24 24', 'aria-hidden': props.label ? undefined : 'true', role: props.label ? 'img' : undefined, 'aria-label': props.label },
      d.map(function (p, i) { return h('path', { key: i, d: p }); }));
  }
  Icon.names = Object.keys(PATHS);

  /* ---------------- Backdrop / Shell / Glass ---------------- */
  function Backdrop(props) {
    var style = Object.assign({}, props.style);
    if (props.image) {
      style.backgroundImage = 'linear-gradient(var(--scrim), var(--scrim)), url("' + props.image + '")';
    }
    return h('div', Object.assign(rest(props, ['image', 'className', 'style', 'children']), { className: cx('sta-backdrop', props.image && 'sta-backdrop--photo', props.className), style: style }), props.children);
  }

  function Glass(props) {
    var v = props.variant || 'base';
    var Tag = props.as || 'section';
    return h(Tag, Object.assign(rest(props, ['variant', 'padded', 'as', 'className', 'title', 'actions', 'children']), {
      className: cx('sta-glass', v === 'strong' && 'sta-glass--strong', v === 'inset' && 'sta-glass--inset', props.padded !== false && 'sta-glass--pad', props.className)
    }),
      (props.title || props.actions) ? h('div', { className: 'sta-panel-head' }, props.title ? h('h2', { className: 'sta-panel-title' }, props.title) : h('span'), props.actions || null) : null,
      props.children);
  }

  function Shell(props) {
    return h('div', { className: cx('sta-shell sta-glass', props.className), style: props.style },
      props.nav || null,
      h('main', { className: 'sta-shell__body' }, props.children),
      props.chat === false ? null : h(ChatFab, { style: { right: 24, bottom: 24 } }));
  }

  /* ---------------- TopNav ---------------- */
  function TopNav(props) {
    var items = props.items || [];
    return h('header', { className: 'sta-nav' },
      h('a', { className: 'sta-brand', href: props.homeHref || '#', 'aria-label': (props.brand || 'AVIANCO') + ', inicio' }, props.brand || 'AVIANCO'),
      h('nav', { className: 'sta-nav__items', 'aria-label': 'Principal' },
        items.map(function (it, i) {
          return h('a', { key: i, className: 'sta-nav__item', href: it.href || '#', 'aria-current': it.active ? 'page' : undefined, onClick: it.onClick },
            it.icon ? h(Icon, { name: it.icon }) : null, it.label);
        })),
      h('div', { className: 'sta-nav__right' },
        props.right || null,
        props.user ? h('div', { className: 'sta-user' },
          h('span', { className: 'sta-avatar', 'aria-hidden': 'true' }, initials(props.user.name)),
          h('span', null, h('span', { className: 'sta-user__name' }, props.user.name), props.user.role ? h('span', { className: 'sta-user__role' }, props.user.role) : null))
          : null));
  }
  function initials(name) {
    return String(name || '').split(/\s+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
  }

  /* ---------------- Button / Badge / Segmented ---------------- */
  function Button(props) {
    var v = props.variant || 'secondary';
    var Tag = props.href ? 'a' : 'button';
    return h(Tag, Object.assign(rest(props, ['variant', 'size', 'icon', 'iconAfter', 'block', 'className', 'children']), {
      className: cx('sta-btn', 'sta-btn--' + v, props.size === 'sm' && 'sta-btn--sm', props.block && 'sta-btn--block', props.className),
      type: Tag === 'button' ? (props.type || 'button') : undefined
    }),
      props.icon ? h(Icon, { name: props.icon }) : null,
      props.children,
      props.iconAfter ? h(Icon, { name: props.iconAfter }) : null);
  }

  function Badge(props) {
    var tone = props.tone || 'neutral';
    return h('span', { className: cx('sta-badge', tone !== 'neutral' && 'sta-badge--' + tone, props.className) },
      props.icon ? h(Icon, { name: props.icon }) : null, props.children);
  }

  function Segmented(props) {
    var opts = props.options || [];
    var st = useState(props.defaultValue != null ? props.defaultValue : (opts[0] && (opts[0].value != null ? opts[0].value : opts[0])));
    var value = props.value != null ? props.value : st[0];
    return h('div', { className: cx('sta-seg', props.className), role: 'group', 'aria-label': props.label },
      opts.map(function (o) {
        var val = o.value != null ? o.value : o, lab = o.label != null ? o.label : o;
        return h('button', { key: val, type: 'button', className: 'sta-seg__opt', 'aria-pressed': value === val ? 'true' : 'false',
          onClick: function () { st[1](val); if (props.onChange) props.onChange(val); } }, lab);
      }));
  }

  /* ---------------- Field / SearchPill ---------------- */
  var fieldSeq = 0;
  function Field(props) {
    var idRef = React.useRef(null);
    if (!idRef.current) idRef.current = props.id || ('sta-f' + (++fieldSeq));
    var id = idRef.current;
    var isSelect = !!props.options;
    var control = isSelect
      ? h('select', { id: id, className: 'sta-input', defaultValue: props.value, 'aria-invalid': props.error ? 'true' : undefined, 'aria-describedby': (props.error || props.hint) ? id + '-m' : undefined, onChange: props.onChange },
          props.options.map(function (o) { var v = o.value != null ? o.value : o; return h('option', { key: v, value: v }, o.label != null ? o.label : o); }))
      : h('input', Object.assign(rest(props, ['label', 'hint', 'error', 'icon', 'options', 'value', 'className', 'id']), { id: id, className: 'sta-input', defaultValue: props.value, 'aria-invalid': props.error ? 'true' : undefined, 'aria-describedby': (props.error || props.hint) ? id + '-m' : undefined }));
    var msg = props.error || props.hint;
    return h('div', { className: cx('sta-field', props.error && 'sta-field--error', props.icon && 'sta-field--icon', isSelect && 'sta-field--select', props.className) },
      props.label ? h('label', { className: 'sta-field__label', htmlFor: id }, props.label) : null,
      h('div', { className: 'sta-field__control' },
        props.icon ? h('span', { className: 'sta-field__lead' }, h(Icon, { name: props.icon })) : null,
        control,
        isSelect ? h('span', { className: 'sta-field__trail' }, h(Icon, { name: 'chevron-down' })) : null),
      msg ? h('div', { className: 'sta-field__msg', id: id + '-m', role: props.error ? 'alert' : undefined }, props.error ? h(Icon, { name: 'alert' }) : null, msg) : null);
  }

  function SearchPill(props) {
    return h('label', { className: cx('sta-search', props.className), style: props.style },
      h(Icon, { name: 'search' }),
      h('input', { type: 'search', placeholder: props.placeholder || 'Buscar', defaultValue: props.value, 'aria-label': props.label || props.placeholder || 'Buscar' }),
      props.onFilters !== false ? h('button', { type: 'button', className: 'sta-search__btn', 'aria-label': 'Filtros', onClick: props.onFilters }, h(Icon, { name: 'sliders', size: 'sm' })) : null);
  }

  /* ---------------- StatTile ---------------- */
  function StatTile(props) {
    var d = props.delta;
    return h('div', { className: cx('sta-stat', props.hero && 'sta-stat--hero', props.className), style: props.style },
      h('span', { className: 'sta-stat__label' }, props.label),
      h('div', { className: 'sta-stat__row' },
        h('span', { className: 'sta-stat__value' }, props.value),
        d ? h(Badge, { tone: d.tone || (d.dir === 'down' ? 'danger' : 'success'), icon: d.dir === 'down' ? 'arrow-down' : 'arrow-up' }, d.text) : null),
      props.foot ? h('span', { className: 'sta-stat__foot' }, props.foot) : null,
      props.action || null);
  }

  /* ---------------- FlightPass ---------------- */
  function FlightPass(props) {
    var f = props.from || {}, t = props.to || {};
    var state = props.state || 'default';
    var promo = !!props.oldPrice;
    return h('article', { className: cx('sta-pass', state === 'selected' && 'sta-pass--selected', state === 'soldout' && 'sta-pass--soldout', promo && 'sta-pass--promo', props.className), 'aria-label': 'Vuelo ' + (props.code || '') + ' ' + (f.city || '') + ' a ' + (t.city || '') },
      h('div', { className: 'sta-pass__grid' },
        h('div', { className: 'sta-pass__main' },
          h('div', { className: 'sta-pass__route' },
            h('div', { className: 'sta-pass__end' },
              h('span', { className: 'sta-pass__iata' }, f.iata),
              h('span', { className: 'sta-pass__city' }, f.city + (f.tz ? ' · ' + f.tz : '')),
              h('span', { className: 'sta-pass__time' }, f.time)),
            h('div', { className: 'sta-pass__line' },
              h('div', { className: 'sta-pass__track' }, h(Icon, { name: 'plane' })),
              h('span', { className: 'sta-pass__dur' }, props.duration || 'Directo')),
            h('div', { className: 'sta-pass__end sta-pass__end--to' },
              h('span', { className: 'sta-pass__iata' }, t.iata),
              h('span', { className: 'sta-pass__city' }, t.city + (t.tz ? ' · ' + t.tz : '')),
              h('span', { className: 'sta-pass__time' }, t.time))),
          (props.badges || props.note || props.date) ? h('div', { className: 'sta-pass__meta' },
            props.date ? h('span', null, props.date) : null,
            (props.badges || []).map(function (b, i) { return h(Badge, { key: i, tone: b.tone, icon: b.icon }, b.label); }),
            props.note ? h('span', null, props.note) : null) : null),
        h('div', { className: 'sta-pass__stub' },
          h('div', null,
            h('div', { className: 'sta-pass__code' }, props.code),
            promo ? h('div', { className: 'sta-pass__old' }, props.oldPrice) : null,
            h('div', { className: 'sta-pass__price' }, props.price),
            props.priceNote ? h('div', { className: 'sta-pass__note' }, props.priceNote) : null),
          props.action || null)));
  }

  /* ---------------- Board ---------------- */
  function Board(props) {
    var cols = props.columns || [];
    return h('div', { className: 'sta-board-wrap' },
      h('table', { className: 'sta-board' },
        props.caption ? h('caption', { style: { position: 'absolute', left: -9999 } }, props.caption) : null,
        h('thead', null, h('tr', null, cols.map(function (c) { return h('th', { key: c.key, className: c.align === 'right' ? 'is-num' : undefined, scope: 'col' }, c.label); }))),
        h('tbody', null, (props.rows || []).map(function (r, i) {
          return h('tr', { key: r.id || i, className: (props.highlight === i) ? 'is-hl' : undefined },
            cols.map(function (c) {
              var v = c.render ? c.render(r) : r[c.key];
              return h('td', { key: c.key, className: c.align === 'right' ? 'is-num' : undefined }, v);
            }));
        }))));
  }
  function Flap(props) { return h('span', { className: 'sta-flap' }, props.children); }
  Board.Flap = Flap;

  function Meter(props) {
    var pct = Math.max(0, Math.min(100, (props.value / props.max) * 100));
    return h('span', { className: 'sta-meter', 'aria-label': props.value + ' de ' + props.max + ' sillas vendidas o reservadas' },
      h('span', { className: 'sta-meter__track' }, h('span', { className: 'sta-meter__fill', style: { width: pct + '%' } })),
      h('span', null, props.value, h('span', { className: 'sta-meter__of' }, '/' + props.max)));
  }

  /* ---------------- SeatMap (nacional AB|CDE, Apéndice A del SRS) ---------------- */
  var LETTERS = ['A', 'B', 'C', 'D', 'E'];
  function SeatMap(props) {
    var firstRows = props.firstRows || 5, rows = props.rows || 30;
    var from = props.fromRow || 1, to = props.toRow || rows;
    var taken = {}; (props.taken || []).forEach(function (s) { taken[s] = true; });
    var st = useState(props.selected || null);
    var selected = props.onSelect ? props.selected : st[0];
    function pick(code) { if (props.onSelect) props.onSelect(code); else st[1](code); }
    var dimFirst = props.ticketClass === 'economica', dimEco = props.ticketClass === 'primera';

    function row(n) {
      var dim = n <= firstRows ? dimFirst : dimEco;
      var cells = [h('span', { key: 'n', className: 'sta-cabin__num' }, n)];
      LETTERS.forEach(function (L, i) {
        if (i === 2) cells.push(h('span', { key: 'aisle' }));
        var code = n + L;
        var isCur = code === props.current, isSel = code === selected, isTaken = taken[code];
        var cls = cx('sta-seat', isTaken && 'sta-seat--taken', isCur && 'sta-seat--current', isSel && 'sta-seat--selected');
        var label = 'Silla ' + code + ', ' + (isCur ? 'tu silla actual' : isSel ? 'seleccionada' : isTaken ? 'ocupada' : dim ? 'de otra clase' : 'libre');
        cells.push(h('button', { key: code, type: 'button', className: cls, disabled: isTaken || dim, 'aria-label': label, 'aria-pressed': isSel ? 'true' : undefined, title: label,
          onClick: function () { if (!isCur) pick(code); } }, (isCur || isSel) ? code : ''));
      });
      return h('div', { key: n, className: cx('sta-cabin__row', dim && 'sta-cabin__dim') }, cells);
    }
    var body = [];
    for (var n = from; n <= to; n++) {
      if (n === from && n <= firstRows) body.push(h('div', { key: 'c1', className: 'sta-cabin__class sta-cabin__class--first' }, 'Primera clase · filas 1 a ' + firstRows));
      if (n === firstRows + 1) body.push(h('div', { key: 'c2', className: cx('sta-cabin__class', from <= firstRows && 'sta-cabin__class--split') }, 'Económica · filas ' + (firstRows + 1) + ' a ' + rows));
      body.push(row(n));
    }
    return h('div', { className: cx('sta-cabin', props.className), role: 'group', 'aria-label': 'Mapa de sillas' },
      h('div', { className: 'sta-cabin__letters' }, h('span'), h('span', null, 'A'), h('span', null, 'B'), h('span'), h('span', null, 'C'), h('span', null, 'D'), h('span', null, 'E')),
      h('div', { className: 'sta-cabin__scroll', style: props.maxHeight ? { maxHeight: props.maxHeight } : undefined }, body),
      props.footer ? h('div', { className: 'sta-cabin__foot' }, props.footer) : null);
  }
  function SeatLegend() {
    function item(cls, text) { return h('div', { className: 'sta-legend__item' }, h('span', { className: cx('sta-seat', cls), 'aria-hidden': 'true' }), text); }
    return h('div', { className: 'sta-legend' }, item('', 'Libre'), item('sta-seat--taken', 'Ocupada'), item('sta-seat--current', 'Tu silla actual'), item('sta-seat--selected', 'La que eliges'));
  }
  SeatMap.Legend = SeatLegend;

  /* ---------------- Dialog ---------------- */
  function Dialog(props) {
    var panel = h('div', { className: 'sta-dialog', role: 'dialog', 'aria-modal': props.inline ? undefined : 'true', 'aria-labelledby': 'sta-dlg-t' },
      h('h2', { className: 'sta-dialog__title', id: 'sta-dlg-t' }, props.title),
      props.subtitle ? h('p', { className: 'sta-dialog__sub' }, props.subtitle) : null,
      props.notice ? h('div', { className: cx('sta-notice', props.tone && 'sta-notice--' + props.tone) }, h(Icon, { name: props.tone === 'danger' ? 'alert' : 'info' }), h('div', null, props.notice)) : null,
      h('div', { className: 'sta-dialog__body' }, props.children),
      props.actions ? h('div', { className: 'sta-dialog__actions' }, props.actions) : null);
    if (props.inline) return panel;
    return h('div', { className: 'sta-scrim' }, panel);
  }

  /* ---------------- ChatFab ---------------- */
  function ChatFab(props) {
    return h('button', { type: 'button', className: cx('sta-chatfab', props.static && 'sta-chatfab--static', props.className), style: props.style, onClick: props.onClick, 'aria-label': 'Información: abrir el asistente' },
      h('span', { className: 'sta-chatfab__dot' }, h(Icon, { name: 'info' })), props.label || 'Información');
  }

  var ns = { Backdrop: Backdrop, Shell: Shell, TopNav: TopNav, Glass: Glass, Button: Button, Badge: Badge, Segmented: Segmented, Field: Field, SearchPill: SearchPill, StatTile: StatTile, FlightPass: FlightPass, Board: Board, Meter: Meter, SeatMap: SeatMap, Dialog: Dialog, ChatFab: ChatFab, Icon: Icon };
  /* Formato de la interfaz (IU-05, IU-06 del SRS) */
  ns.cop = function (n, opts) {
    var s = '$ ' + Math.abs(Math.round(n)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    if (opts && opts.sign) return (n < 0 ? '− ' : '+ ') + s;
    return (n < 0 ? '− ' : '') + s;
  };
  window.STA = Object.assign(window.STA || {}, ns);
})();
