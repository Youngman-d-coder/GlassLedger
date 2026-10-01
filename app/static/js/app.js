document.addEventListener('DOMContentLoaded', () => {
  const sidebarToggle = document.querySelector('#sidebarToggle');
  const sidebar = document.querySelector('#sidebar');
  if (sidebarToggle && sidebar) {
    const saved = localStorage.getItem('glassledger-sidebar');
    if (saved === 'collapsed') sidebar.classList.add('collapsed');
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      localStorage.setItem('glassledger-sidebar', sidebar.classList.contains('collapsed') ? 'collapsed' : 'expanded');
    });
  }

  const quick = document.querySelector('[data-quick-toggle]');
  const menu = document.querySelector('#quickMenu');
  if (quick && menu) quick.addEventListener('click', () => menu.classList.toggle('open'));

  document.querySelectorAll('[data-count]').forEach(el => {
    const target = Number(el.dataset.count || 0);
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let n = 0;
    const step = Math.max(1, Math.ceil(target / 18));
    const timer = setInterval(() => {
      n = Math.min(target, n + step);
      el.textContent = n;
      if (n >= target) clearInterval(timer);
    }, 25);
  });

  const itemSelect = document.querySelector('#itemSelect');
  const unitSelect = document.querySelector('#unitSelect');
  const qtyInput = document.querySelector('#quantityInput');
  if (itemSelect && unitSelect && window.GLASSLEDGER_TX) {
    let data = null;
    const txType = window.GLASSLEDGER_TX.txType;
    const isOut = ['ISSUE','RETURN_OUT','ADJUSTMENT_OUT','EXPIRED','DAMAGED'].includes(txType);
    async function loadItem() {
      const base = window.GLASSLEDGER_TX.dataUrl.replace('/0/unit-data', `/${itemSelect.value}/unit-data`);
      const res = await fetch(base, {headers: {'X-Requested-With':'fetch'}});
      data = await res.json();
      unitSelect.innerHTML = '';
      data.units.forEach(u => {
        const opt = new Option(u.name, u.id);
        const preferred = ['RECEIPT','OPENING_BALANCE','RETURN_IN'].includes(txType) ? data.preferred_receive_unit_id : data.preferred_issue_unit_id;
        if (preferred && Number(preferred) === Number(u.id)) opt.selected = true;
        opt.dataset.factor = u.factor;
        unitSelect.add(opt);
      });
      document.querySelector('#currentStock').textContent = data.balance_label;
      const wrap = document.querySelector('#batchIssueWrap');
      const batchSelect = document.querySelector('#batchSelect');
      if (wrap && batchSelect) {
        wrap.hidden = !(data.batch_tracking && isOut);
        batchSelect.required = data.batch_tracking && isOut;
        batchSelect.innerHTML = '<option value="">Select batch</option>';
        data.batches.forEach((b, idx) => {
          const opt = new Option((idx === 0 ? 'FEFO • ' : '') + b.label, b.id);
          batchSelect.add(opt);
        });
      }
      updatePreview();
    }
    function updatePreview() {
      if (!data) return;
      const opt = unitSelect.options[unitSelect.selectedIndex];
      const qty = Number(qtyInput.value || 0);
      const factor = Number(opt?.dataset.factor || 1);
      const baseQty = qty * factor;
      const sign = isOut ? -1 : 1;
      const projected = Math.max(0, data.balance + sign * baseQty);
      document.querySelector('#conversionHint').textContent = qty ? `${qty} ${opt.text} = ${baseQty} ${data.base_unit}${baseQty === 1 ? '' : 's'}` : `1 ${opt?.text || ''} = ${factor} ${data.base_unit}${factor === 1 ? '' : 's'}`;
      document.querySelector('#afterStock').textContent = qty ? `Projected base balance: ${projected}` : '';
    }
    itemSelect.addEventListener('change', loadItem);
    unitSelect.addEventListener('change', updatePreview);
    qtyInput.addEventListener('input', updatePreview);
    loadItem().catch(() => { document.querySelector('#conversionHint').textContent = 'Could not load unit data.'; });
  }
});
