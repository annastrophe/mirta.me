/* Click-to-play: nothing from Instagram loads until the visitor taps the cover. */
(function () {
  document.querySelectorAll('.reel-frame[data-embed]').forEach(function (frame) {
    var link = frame.querySelector('.reel-play');
    if (!link) return;
    link.addEventListener('click', function (e) {
      e.preventDefault();
      var f = document.createElement('iframe');
      f.src = frame.getAttribute('data-embed');
      f.title = 'Instagram reel';
      f.allow = 'autoplay; encrypted-media; picture-in-picture';
      f.setAttribute('allowfullscreen', '');
      f.loading = 'eager';
      frame.innerHTML = '';
      frame.appendChild(f);
      frame.classList.add('is-playing');
    });
  });
})();
