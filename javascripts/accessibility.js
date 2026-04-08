// Material theme renders the search container as role="dialog" but omits aria-label.
// Lighthouse flags this as an ARIA violation. Patch it post-load.
document.addEventListener("DOMContentLoaded", function () {
  var searchDialog = document.querySelector('.md-search[role="dialog"]');
  if (searchDialog && !searchDialog.getAttribute("aria-label")) {
    searchDialog.setAttribute("aria-label", "Search");
  }
});
