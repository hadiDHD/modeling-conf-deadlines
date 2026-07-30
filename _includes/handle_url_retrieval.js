// Get subjects from URL/Cache
var url = new URL(window.location);
subs = url.searchParams.get("sub");
if (subs == undefined) {
  subs = store.get("{{site.domain}}-subs");
} else {
  subs = subs.toUpperCase().split(",");
}

// Apply selections
if (subs == undefined) {
  subs = all_subs;
} else {
  subs = subs.filter(function(s) {
    return all_subs.indexOf(s) > -1;
  });
}
$("#subject-select").multiselect("select", subs);

// Cascading venue filter options based on the loaded/cached subjects
update_venue_options_from_subjects(subs);

// Get venues from URL/Cache
var venues_param = url.searchParams.get("venue");
if (venues_param == undefined) {
  venues = store.get("{{site.domain}}-venues");
} else {
  venues = venues_param.split(",");
}

// Apply selections for venues
if (venues == undefined || venues.length === 0) {
  venues = all_venues;
} else {
  venues = venues.filter(function(v) {
    return all_venues.indexOf(v) > -1;
  });
  if (venues.length === 0) {
    venues = all_venues;
  }
}
$("#venue-select").multiselect("deselectAll", false);
$("#venue-select").multiselect("select", venues);

update_filtering({ subs: subs, all_subs: all_subs, venues: venues, all_venues: all_venues });
