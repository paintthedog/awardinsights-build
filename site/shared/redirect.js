/*! © 2026 Award Insights · awardinsights.org · All rights reserved. */
/* Old .html addresses: go to the clean URL, keeping the #… part so shared links still open the same view. */
location.replace(document.querySelector('link[rel="canonical"]').getAttribute("href") + location.hash);
