// Borrowed from https://github.com/moment/moment-timezone/issues/167
// Adds support for time zones 'UTC-12'..'UTC+12'
function addUtcTimeZones() {
  // Moment.js uses the IANA timezone database, which supports generic time zones like 'Etc/GMT+1'.
  // However, the signs for these time zones are inverted compared to ISO 8601.
  // For more details, see https://github.com/moment/moment-timezone/issues/167
  for (let offset = -12; offset <= 12; offset++) {
    const posixSign = offset <= 0 ? "+" : "-";
    const isoSign = offset >= 0 ? "+" : "-";
    const link = `Etc/GMT${posixSign}${Math.abs(
      offset
    )}|UTC${isoSign}${Math.abs(offset)}`;
    moment.tz.link(link);
  }
}

function update_filtering(data) {
  var page_url = "{{site.baseurl}}";
  store.set("{{site.domain}}-subs", data.subs);
  if (data.venues) {
    store.set("{{site.domain}}-venues", data.venues);
  }

  var active_venues = data.venues || (typeof venues !== 'undefined' ? venues : []);

  $(".ConfItem").each(function() {
    var $item = $(this);
    var matchesSubject = false;
    for (var i = 0; i < data.subs.length; i++) {
      if ($item.hasClass(data.subs[i] + "-conf")) {
        matchesSubject = true;
        break;
      }
    }
    var itemVenue = $item.attr("data-venue");
    var matchesVenue = active_venues.includes(itemVenue);
    if (matchesSubject && matchesVenue) {
      $item.show();
    } else {
      $item.hide();
    }
  });

  var urlParams = new URLSearchParams();
  if (data.subs.length > 0) {
    urlParams.set("sub", data.subs.join());
  }
  if (active_venues.length > 0) {
    urlParams.set("venue", active_venues.join());
  }
  var queryString = urlParams.toString();
  if (queryString.length > 0) {
    window.history.pushState("", "", page_url + "/?" + queryString);
  } else {
    window.history.pushState("", "", page_url);
  }
}

function createCalendarFromObject(data) {
  return createCalendar({
    options: {
      class: "calendar-obj",

      // You can pass an ID. If you don't, one will be generated for you
      id: data.id,
    },
    data: {
      // Event title
      title: data.title,

      // Event start date
      start: data.date,

      // Event duration
      duration: 60,
    },
  });
}

function update_venue_options_from_subjects(subs) {
  var new_all_venues = [];
  if ($("#calendar-page").length > 0) {
    // Calendar Page: use conf_list_all
    var available_venues_set = new Set();
    if (typeof conf_list_all !== "undefined") {
      conf_list_all.forEach(function(v) {
        var matchesSubject = false;
        for (var i = 0; i < subs.length; i++) {
          if (v.subject.indexOf(subs[i]) > -1) {
            matchesSubject = true;
            break;
          }
        }
        if (matchesSubject && v.venue) {
          available_venues_set.add(v.venue);
        }
      });
    }
    new_all_venues = Array.from(available_venues_set).sort();
  } else {
    // Countdown Page: use ConfItem DOM elements
    var available_venues_set = new Set();
    $(".ConfItem").each(function() {
      var $item = $(this);
      var matchesSubject = false;
      for (var i = 0; i < subs.length; i++) {
        if ($item.hasClass(subs[i] + "-conf")) {
          matchesSubject = true;
          break;
        }
      }
      if (matchesSubject) {
        var venue = $item.attr("data-venue");
        if (venue) {
          available_venues_set.add(venue);
        }
      }
    });
    new_all_venues = Array.from(available_venues_set).sort();
  }

  // If we had all selected before, or if venues is empty/equal to all_venues, select all of the new ones.
  var had_all_selected = (typeof venues === 'undefined' || typeof all_venues === 'undefined' || venues.length === 0 || all_venues.every(function(v) { return venues.includes(v); }));
  if (had_all_selected) {
    venues = new_all_venues.slice();
  } else {
    venues = venues.filter(function(v) {
      return new_all_venues.indexOf(v) > -1;
    });
    if (venues.length === 0 && new_all_venues.length > 0) {
      venues = new_all_venues.slice();
    }
  }

  var $venueSelect = $("#venue-select");
  $venueSelect.empty();
  new_all_venues.forEach(function(v) {
    $venueSelect.append('<option value="' + v + '">' + v + '</option>');
  });

  all_venues = new_all_venues;

  $venueSelect.multiselect('rebuild');
  $venueSelect.multiselect('deselectAll', false);
  $venueSelect.multiselect('select', venues);
}
