/* Website analytics: honour the owner's GoatCounter browser exclusion. */
(function () {
  'use strict';
  var id = 'G-KMZMZG11Z3';
  var excluded = false;
  try { excluded = localStorage.getItem('skipgc') === 't'; } catch (e) {}
  if (location.hash === '#analytics-exclude') {
    excluded = true;
    try { localStorage.setItem('skipgc', 't'); } catch (e) {}
    alert('Your visits are excluded from website analytics in this browser.');
    history.replaceState(null, '', location.pathname + location.search);
  }
  window['ga-disable-' + id] = excluded;
  if (excluded || location.hash === '#toggle-goatcounter' ||
      location.hostname !== 'chiragmirani.github.io') return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag('js', new Date());
  window.gtag('config', id, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false
  });
  var tag = document.createElement('script');
  tag.async = true;
  tag.src = 'https://www.googletagmanager.com/gtag/js?id=' + id;
  document.head.appendChild(tag);
  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[data-goatcounter-click]');
    if (!link) return;
    var action = link.getAttribute('data-goatcounter-click');
    var eventName = action === 'professional-linkedin' ? 'linkedin_click' :
      action.indexOf('app-store-') === 0 ? 'app_store_click' : 'research_click';
    window.gtag('event', eventName, {
      link_id: action,
      link_url: link.href,
      link_text: link.getAttribute('data-goatcounter-title') || link.textContent.trim()
    });
  });
}());
