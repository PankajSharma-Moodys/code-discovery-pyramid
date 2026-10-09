package com.acme.res;

import javax.ws.rs.POST;
import javax.ws.rs.Path;

@Path("/v1/reservations")
public class ReservationResource {

    private final ReservationService reservationService;

    public ReservationResource(ReservationService reservationService) {
        this.reservationService = reservationService;
    }

    @POST
    public Reservation makeReservations(Reservation reservation) {
        return this.reservationService.makeReservations(reservation, "caller");
    }
}
