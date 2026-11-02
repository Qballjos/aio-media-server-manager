/* Local, sample-data-only showcase. It never calls the manager API. */
(() => {
  const initialise = () => {
    const landing = document.querySelector('.aio-landing');
    if (!landing || landing.dataset.ready) return;
    landing.dataset.ready = 'true';
    landing.classList.add('has-js');
    const frame = landing.querySelector('[data-preview]');
    const tabs = [...landing.querySelectorAll('[data-screen]')];
    const themeButton = landing.querySelector('[data-preview-theme]');
    const status = landing.querySelector('[data-preview-status]');
    const assetRoot = new URL(landing.querySelector('[data-preview-image]').getAttribute('src'), document.baseURI);
    const imageUrl = (theme, name) => new URL(`../${theme}/${name}.png`, assetRoot).href;
    let screen = 'home';
    let theme = 'light';
    const selectScreen = (name, focus = false) => {
      screen = name;
      tabs.forEach(tab => {
        const selected = tab.dataset.screen === name;
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
        if (selected && focus) tab.focus();
      });
      landing.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== name; });
      landing.querySelector('[data-screen-name]').textContent = tabs.find(tab => tab.dataset.screen === name).textContent;
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => selectScreen(tab.dataset.screen));
      tab.addEventListener('keydown', event => {
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (next !== undefined) { event.preventDefault(); selectScreen(tabs[next].dataset.screen, true); }
      });
    });
    themeButton.addEventListener('click', () => {
      theme = theme === 'light' ? 'dark' : 'light';
      frame.dataset.theme = theme;
      themeButton.setAttribute('aria-pressed', String(theme === 'dark'));
      themeButton.querySelector('span').textContent = themeButton.dataset[theme === 'light' ? 'dark' : 'light'];
      landing.querySelectorAll('[data-preview-image]').forEach(img => { img.src = imageUrl(theme, img.dataset.previewImage); });
    });
    const pageTheme = () => {
      const pageDark = document.body.dataset.mdColorScheme === 'slate';
      landing.querySelectorAll('[data-theme-image]').forEach(img => { img.src = imageUrl(pageDark ? 'dark' : 'light', img.dataset.themeImage); });
    };
    new MutationObserver(pageTheme).observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });
    pageTheme();

    const lab = landing.querySelector('[data-widget-lab]');
    const grid = lab.querySelector('[data-demo-grid]');
    const widgets = [...grid.querySelectorAll('[data-widget]')];
    const editButton = lab.querySelector('[data-edit]');
    const toolbar = lab.querySelector('[data-demo-toolbar]');
    const addButton = lab.querySelector('[data-add]');
    let editing = false;
    let dragged = null;
    const announce = text => { status.textContent = text; };
    const updateAdd = () => { addButton.disabled = !widgets.some(widget => widget.hidden); };
    const setEditing = value => {
      editing = value;
      lab.classList.toggle('is-editing', value);
      toolbar.hidden = !value;
      editButton.setAttribute('aria-pressed', String(value));
      editButton.querySelector('span').textContent = editButton.dataset[value ? 'doneLabel' : 'editLabel'];
      widgets.forEach(widget => { widget.draggable = value; widget.tabIndex = value ? 0 : -1; });
      lab.querySelectorAll('.demo-search-form input, .demo-search-form button').forEach(control => { control.disabled = value; });
      updateAdd();
    };
    const move = (widget, direction) => {
      const visible = [...grid.children].filter(child => !child.hidden);
      const index = visible.indexOf(widget);
      const other = visible[index + direction];
      if (!other) return;
      const focused = document.activeElement;
      if (direction < 0) grid.insertBefore(widget, other);
      else grid.insertBefore(other, widget);
      if (focused && widget.contains(focused)) focused.focus({ preventScroll: true });
      announce(`${widget.getAttribute('aria-label')} · ${direction < 0 ? widget.querySelector('[data-move="-1"]').getAttribute('aria-label') : widget.querySelector('[data-move="1"]').getAttribute('aria-label')}`);
    };
    const resize = widget => {
      widget.classList.toggle('is-wide');
      widget.querySelector('[data-resize]').setAttribute('aria-pressed', String(widget.classList.contains('is-wide')));
      announce(`${widget.getAttribute('aria-label')} · ${widget.querySelector('[data-resize]').getAttribute('aria-label')}`);
    };
    editButton.addEventListener('click', () => setEditing(!editing));
    addButton.addEventListener('click', () => {
      const widget = widgets.find(item => item.hidden);
      if (widget) { widget.hidden = false; updateAdd(); widget.focus(); announce(`${addButton.textContent.trim()} · ${widget.getAttribute('aria-label')}`); }
    });
    lab.querySelector('[data-reset]').addEventListener('click', () => {
      widgets.forEach(widget => { grid.appendChild(widget); widget.hidden = widget.dataset.defaultHidden === 'true'; widget.classList.toggle('is-wide', widget.dataset.defaultWide === 'true'); widget.querySelector('[data-resize]').setAttribute('aria-pressed', String(widget.classList.contains('is-wide'))); });
      updateAdd(); announce(lab.querySelector('[data-reset]').textContent.trim());
    });
    widgets.forEach(widget => {
      widget.querySelectorAll('[data-move]').forEach(button => button.addEventListener('click', () => { if (editing) move(widget, Number(button.dataset.move)); }));
      const remove = () => { widget.hidden = true; updateAdd(); addButton.focus(); announce(`${widget.getAttribute('aria-label')} · ${widget.querySelector('[data-remove]').getAttribute('aria-label')}`); };
      widget.querySelector('[data-remove]').addEventListener('click', () => { if (editing) remove(); });
      const handle = widget.querySelector('[data-resize]');
      let startX = 0;
      let didResize = false;
      handle.addEventListener('pointerdown', event => { startX = event.clientX; didResize = false; handle.setPointerCapture(event.pointerId); });
      handle.addEventListener('pointermove', event => {
        if (editing && handle.hasPointerCapture(event.pointerId) && !didResize && Math.abs(event.clientX - startX) > 25) { resize(widget); didResize = true; }
      });
      handle.addEventListener('click', () => { if (editing && !didResize) resize(widget); didResize = false; });
      widget.addEventListener('keydown', event => {
        if (!editing || event.target !== widget) return;
        if (['ArrowLeft', 'ArrowRight', 'Delete', 'Backspace'].includes(event.key)) {
          event.preventDefault();
          if (event.key === 'ArrowLeft') move(widget, -1);
          else if (event.key === 'ArrowRight') move(widget, 1);
          else remove();
        }
        if (event.key === 'Escape') { setEditing(false); editButton.focus(); }
      });
      // Pointer capture gives the visible grip the same basic operation on
      // phones, where native HTML drag-and-drop is not reliably available.
      const grip = widget.querySelector('.demo-grip');
      let pointerTarget = null;
      const clearTarget = () => { if (pointerTarget) pointerTarget.classList.remove('is-drop-target'); pointerTarget = null; };
      grip.addEventListener('pointerdown', event => {
        if (!editing || event.button !== 0) return;
        event.preventDefault(); event.stopPropagation();
        grip.setPointerCapture(event.pointerId); widget.classList.add('is-dragging');
      });
      grip.addEventListener('pointermove', event => {
        if (!grip.hasPointerCapture(event.pointerId)) return;
        clearTarget();
        const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-widget]');
        if (target && target !== widget && grid.contains(target) && !target.hidden) { pointerTarget = target; pointerTarget.classList.add('is-drop-target'); }
      });
      const finishPointer = event => {
        if (!grip.hasPointerCapture(event.pointerId)) return;
        if (event.type === 'pointerup' && pointerTarget) {
          const order = [...grid.children];
          if (order.indexOf(widget) < order.indexOf(pointerTarget)) pointerTarget.after(widget);
          else pointerTarget.before(widget);
          widget.focus({ preventScroll: true });
        }
        clearTarget(); widget.classList.remove('is-dragging');
        grip.releasePointerCapture(event.pointerId);
      };
      grip.addEventListener('pointerup', finishPointer);
      grip.addEventListener('pointercancel', finishPointer);
      widget.addEventListener('dragstart', event => {
        if (!editing || event.target.closest('button')) { event.preventDefault(); return; }
        dragged = widget; widget.classList.add('is-dragging'); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', widget.dataset.widget);
      });
      widget.addEventListener('dragover', event => { if (editing && dragged && dragged !== widget) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; } });
      widget.addEventListener('drop', event => {
        event.preventDefault();
        if (editing && dragged && dragged !== widget) { const order = [...grid.children]; if (order.indexOf(dragged) < order.indexOf(widget)) widget.after(dragged); else widget.before(dragged); dragged.focus(); }
      });
      widget.addEventListener('dragend', () => { widget.classList.remove('is-dragging'); dragged = null; });
    });
    landing.querySelector('[data-try-widgets]').addEventListener('click', () => { selectScreen('home'); setEditing(true); editButton.focus({ preventScroll: true }); });
    const searchInput = lab.querySelector('[data-demo-search]');
    const samplePosters = [...lab.querySelectorAll('[data-sample-title]')];
    const sampleReleases = [...lab.querySelectorAll('[data-release-title]')];
    const count = lab.querySelector('[data-demo-count]');
    const filterLibrary = () => {
      const query = searchInput.value.trim().toLocaleLowerCase();
      samplePosters.forEach(poster => { poster.hidden = !poster.dataset.sampleTitle.toLocaleLowerCase().includes(query); });
      sampleReleases.forEach(release => { release.hidden = !release.dataset.releaseTitle.toLocaleLowerCase().includes(query); });
      const matches = samplePosters.filter(poster => !poster.hidden).length;
      count.textContent = String(matches);
      count.setAttribute('aria-label', `${matches} · ${count.dataset.resultsLabel}`);
      lab.querySelector('[data-demo-no-results]').hidden = matches !== 0;
    };
    searchInput.addEventListener('input', filterLibrary);
    lab.querySelector('[data-demo-search-form]').addEventListener('submit', event => { event.preventDefault(); filterLibrary(); });
    lab.querySelector('[data-reset]').addEventListener('click', () => { searchInput.value = ''; filterLibrary(); });
    setEditing(false);
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) { entry.target.classList.add('has-entered'); observer.unobserve(entry.target); }
      }), { threshold: 0.08 });
      landing.querySelectorAll('.landing-section').forEach(section => observer.observe(section));
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialise);
  else initialise();
})();
