$(document).ready(function() {
    const musicMasterVolume = $("#music-master-volume");
    musicMasterVolume.slider({});
    musicMasterVolume.on("slideStop", function(slideEvt) {
        sendCmdSetMusicMasterVolume(slideEvt.value);
    });

    const trackListVolume = $(".track-list-volume");
    trackListVolume.slider({});
    trackListVolume.on("slideStop", function(slideEvt) {
        const target = $(slideEvt.currentTarget);
        const groupIndex = target.data("group-index");
        const trackListIndex = target.data("track-list-index");
        sendCmdSetTrackListVolume(groupIndex, trackListIndex, slideEvt.value);
    });
});