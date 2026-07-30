// Multi-select handler
$("#subject-select").multiselect({
  includeSelectAllOption: true,
  numberDisplayed: 5,
  onChange: function (option, checked, select) {
    var csub = $(option).val();
    if (checked == true) {
      if (subs.indexOf(csub) < 0) subs.push(csub);
    } else {
      var idx = subs.indexOf(csub);
      if (idx >= 0) subs.splice(idx, 1);
      // In case a conf with multiple types (including this type) is wrongly hid, show all confs with at least one checked type.
      for (var i = 0; i < subs.length; i++) {
        // $('.' + subs[i] + '-conf').show();
      }
    }
    update_venue_options_from_subjects(subs);
    var active_venues = typeof venues !== 'undefined' ? venues : [];
    var active_all_venues = typeof all_venues !== 'undefined' ? all_venues : [];
    update_filtering({ subs: subs, all_subs: all_subs, venues: active_venues, all_venues: active_all_venues });
  },
  onSelectAll: function (options) {
    subs = all_subs;
    update_venue_options_from_subjects(subs);
    var active_venues = typeof venues !== 'undefined' ? venues : [];
    var active_all_venues = typeof all_venues !== 'undefined' ? all_venues : [];
    update_filtering({ subs: subs, all_subs: all_subs, venues: active_venues, all_venues: active_all_venues });
  },
  onDeselectAll: function (options) {
    subs = [];
    update_venue_options_from_subjects(subs);
    var active_venues = typeof venues !== 'undefined' ? venues : [];
    var active_all_venues = typeof all_venues !== 'undefined' ? all_venues : [];
    update_filtering({ subs: subs, all_subs: all_subs, venues: active_venues, all_venues: active_all_venues });
  },
  buttonText: function (options, select) {
    if (options.length === 0) {
      return "None selected";
    } else if (options.length > 2) {
      return options.length + " selected";
    } else {
      var labels = [];
      options.each(function () {
        if ($(this).attr("value") !== undefined) {
          labels.push($(this).attr("value"));
        } else {
          labels.push($(this).html());
        }
      });
      return labels.join(", ") + "";
    }
  },
  buttonTitle: function (options, select) {
    return "";
  },
});
