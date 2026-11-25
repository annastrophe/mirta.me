/* The form works without this script (it posts to FormSubmit and returns to #thanks).
   With it, the request is sent in the background and the page never reloads. */
(function () {
  var form = document.getElementById('book-form');
  if (!form || !window.fetch) return;
  var err = document.getElementById('form-error');
  var btn = document.getElementById('book-submit');
  var label = btn.textContent;
  var thanks = document.getElementById('thanks');
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (form.elements._honey.value) return;
    var data = {};
    new FormData(form).forEach(function (v, k) { if (k !== '_next' && k !== '_honey') data[k] = v; });
    data.Mobile = String(data.Mobile).replace(/\D/g, '').replace(/^65(?=\d{8}$)/, '');
    data._subject = 'mirta.me upgrade plan: ' + data['Current HDB type'] + ' to ' + data['Upgrading to'] + ' (' + data.Name + ')';
    data['Submitted from'] = location.href;
    err.hidden = true;
    btn.disabled = true; btn.textContent = 'Sending…';
    fetch(form.action.replace('formsubmit.co/', 'formsubmit.co/ajax/'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(data)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!(res && (res.success === true || res.success === 'true'))) throw new Error();
      thanks.classList.add('show'); thanks.focus();
    }).catch(function () {
      btn.disabled = false; btn.textContent = label;
      err.textContent = "That didn't go through. Try again, or WhatsApp me on 9710 8150.";
      err.hidden = false;
    });
  });
})();
