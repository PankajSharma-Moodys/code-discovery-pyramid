package com.acme.res;

public class ProcessPendingJob {

    private final ReservationService reservationService;

    public ProcessPendingJob(ReservationService reservationService) {
        this.reservationService = reservationService;
    }

    public void run() {
        this.reservationService.processPendingReservations();
    }
}
