package com.acme.res;

import java.util.List;

public interface ReservationRepository {
    Reservation save(Reservation reservation);

    List<Reservation> findPending();
}
