package svc

/** Lifecycle: NEW -> PAID -> SHIPPED.
  * Only NEW orders can be PAID.
  */
sealed trait Status
case object NEW extends Status
case object PAID extends Status
case object SHIPPED extends Status
