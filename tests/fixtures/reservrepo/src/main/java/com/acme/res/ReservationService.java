package com.acme.res;

import java.util.Optional;

public class ReservationService {

    private final ReservationRepository reservationRepository;
    private final ServerHelper serverHelper;

    public ReservationService(ReservationRepository reservationRepository, ServerHelper serverHelper) {
        this.reservationRepository = reservationRepository;
        this.serverHelper = serverHelper;
    }

    public Reservation makeReservations(Reservation reservation, String owner) {
        this.validateMakeReservation(reservation);
        Optional<Reservation> existing = checkIdempotency(reservation);
        if (existing.isPresent()) {
            return existing.get();
        }
        reservation.setCapacity(this.getReservationCapacity(reservation));
        Reservation saved = reservationRepository.save(reservation);
        return this.initializeUserAndPassword(saved, owner);
    }

    public void processPendingReservations() {
        for (Reservation r : reservationRepository.findPending()) {
            this.initializeUserAndPassword(r, "system");
        }
    }

    protected Reservation initializeUserAndPassword(Reservation reservation, String owner) {
        this.serverHelper.createReservationCredentials(reservation, owner);
        return reservation;
    }

    private void validateMakeReservation(Reservation reservation) {
        if (reservation.getCapacity() == null) {
            throw new IllegalArgumentException("capacity required");
        }
    }

    private Optional<Reservation> checkIdempotency(Reservation reservation) {
        return Optional.empty();
    }

    private Integer getReservationCapacity(Reservation reservation) {
        return reservation.getCapacity();
    }
}
