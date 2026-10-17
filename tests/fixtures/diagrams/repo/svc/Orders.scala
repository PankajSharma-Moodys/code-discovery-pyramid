package svc

class Orders(dao: Dao) {
  private val terminal = Set(NEW, PAID, SHIPPED)

  def pay(id: String): Unit =
    dao.update(id, status = PAID)

  def ship(id: String): Unit = {
    val o = dao.get(id)
    dao.update(id, status = SHIPPED)
  }
}
