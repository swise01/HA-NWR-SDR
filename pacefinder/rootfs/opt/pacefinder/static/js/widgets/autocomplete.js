// Searchable autocomplete widget — vanilla JS, no dependencies.
// Spec: docs/specs/searchable-autocomplete-widget.md
//
// Usage:
//   const ac = Autocomplete.attach(inputEl, {
//     options: [...],            // array of strings (values + labels)
//     allowFreeText: true,       // default false; when true, typed-but-unlisted
//                                // values are accepted on commit
//     emptyText: 'No matches',
//     onSelect: (val) => {...},  // fires when an option is picked or typed-and-committed
//     onChange: (val) => {...},  // fires on every input keystroke
//     initialValue: 'Spa',
//   });
//   ac.setOptions([...]);        // refresh after async load
//   ac.destroy();                // detach event listeners
window.Autocomplete = (function(){
  function _esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  let _idCounter = 0;

  function attach(input, opts){
    opts = opts || {};
    let options = (opts.options || []).map(_normalizeOption);
    const allowFreeText = !!opts.allowFreeText;
    const emptyText = opts.emptyText || 'No matches';
    const onSelect = opts.onSelect || (() => {});
    const onChange = opts.onChange || (() => {});

    const id = 'ac-' + (++_idCounter);
    const listId = id + '-list';

    // Wrap the input in a positioning container (.ac-wrap) so the panel
    // can be positioned absolutely relative to it. If a wrap already
    // exists (e.g. attach called twice), reuse.
    let wrap = input.parentElement && input.parentElement.classList.contains('ac-wrap')
      ? input.parentElement : null;
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'ac-wrap';
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);
    }
    input.classList.add('ac-input');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-controls', listId);

    const caret = document.createElement('button');
    caret.type = 'button';
    caret.className = 'ac-caret';
    caret.tabIndex = -1;
    caret.setAttribute('aria-label', 'Open list');
    caret.innerHTML = '▾';
    wrap.appendChild(caret);

    const panel = document.createElement('div');
    panel.className = 'ac-panel';
    panel.id = listId;
    panel.setAttribute('role', 'listbox');
    panel.style.display = 'none';
    wrap.appendChild(panel);

    let highlighted = -1;
    let isOpen = false;
    let lastFilter = '';

    function _normalizeOption(o){
      if (typeof o === 'string') return { value: o, label: o };
      return o;
    }

    function open(){
      if (isOpen) return;
      isOpen = true;
      input.setAttribute('aria-expanded', 'true');
      render();
      panel.style.display = '';
    }

    function close(){
      if (!isOpen) return;
      isOpen = false;
      highlighted = -1;
      input.setAttribute('aria-expanded', 'false');
      panel.style.display = 'none';
    }

    function filter(){
      const q = (input.value || '').trim().toLowerCase();
      lastFilter = q;
      if (!q) return options.slice();
      return options.filter(o => o.label.toLowerCase().includes(q));
    }

    function render(){
      const matches = filter();
      if (!matches.length) {
        panel.innerHTML = `<div class="ac-empty">${_esc(emptyText)}</div>`;
        return;
      }
      panel.innerHTML = matches.map((o, i) => {
        const cls = 'ac-opt' + (i === highlighted ? ' on' : '');
        return `<div class="${cls}" role="option" data-i="${i}" data-val="${_esc(o.value)}">${_esc(o.label)}</div>`;
      }).join('');
      // Scroll the highlighted option into view if present.
      if (highlighted >= 0) {
        const el = panel.querySelector('.ac-opt.on');
        if (el) el.scrollIntoView({block: 'nearest'});
      }
    }

    function pickIndex(i){
      const matches = filter();
      const opt = matches[i];
      if (!opt) return;
      input.value = opt.value;
      onSelect(opt.value);
      close();
    }

    function commitTyped(){
      // Called on Enter or blur when no option is highlighted.
      // Free-text mode: accept the typed value as-is.
      // Strict mode: revert to the previous selection (i.e. don't change).
      if (allowFreeText) {
        onSelect(input.value.trim());
      }
      close();
    }

    // ── event handlers ────────────────────────────────────────────────
    function onInput(){
      highlighted = -1;
      onChange(input.value);
      open();
      render();
    }
    function onKeyDown(e){
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (!isOpen) open();
        const matches = filter();
        if (!matches.length) return;
        highlighted = (highlighted + 1) % matches.length;
        render();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (!isOpen) open();
        const matches = filter();
        if (!matches.length) return;
        highlighted = (highlighted <= 0 ? matches.length : highlighted) - 1;
        render();
      } else if (e.key === 'Enter') {
        if (isOpen && highlighted >= 0) {
          e.preventDefault();
          pickIndex(highlighted);
        } else {
          commitTyped();
        }
      } else if (e.key === 'Escape') {
        if (isOpen) {
          e.preventDefault();
          close();
        }
      }
    }
    function onPanelClick(e){
      const opt = e.target.closest('.ac-opt');
      if (!opt) return;
      pickIndex(+opt.dataset.i);
    }
    function onCaretClick(e){
      e.preventDefault();
      if (isOpen) { close(); }
      else { input.focus(); open(); }
    }
    function onFocus(){
      open();
    }
    function onDocumentClick(e){
      if (!wrap.contains(e.target)) close();
    }

    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeyDown);
    input.addEventListener('focus', onFocus);
    panel.addEventListener('mousedown', e => e.preventDefault()); // prevent input blur before click fires
    panel.addEventListener('click', onPanelClick);
    caret.addEventListener('click', onCaretClick);
    document.addEventListener('click', onDocumentClick);

    // Initial value
    if (opts.initialValue !== undefined && opts.initialValue !== null) {
      input.value = opts.initialValue;
    }

    return {
      setOptions(newOpts){
        options = (newOpts || []).map(_normalizeOption);
        if (isOpen) render();
      },
      open: open,
      close: close,
      destroy(){
        input.removeEventListener('input', onInput);
        input.removeEventListener('keydown', onKeyDown);
        input.removeEventListener('focus', onFocus);
        document.removeEventListener('click', onDocumentClick);
        // Caret + panel removed when wrap is torn down by the page; safe to leave.
      },
    };
  }

  return { attach };
})();
