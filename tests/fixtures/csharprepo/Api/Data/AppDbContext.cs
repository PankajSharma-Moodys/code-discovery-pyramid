using Microsoft.EntityFrameworkCore;

namespace Acme.Api.Data;

public class AppDbContext : DbContext
{
    public DbSet<Widget> Widgets { get; set; } = null!;
    public DbSet<Gadget> Gadgets { get; set; } = null!;
    public DbSet<Ghost> Ghosts { get; set; } = null!;

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Gadget>(e => { e.ToTable("gadget_items"); });
        modelBuilder.Entity<Ghost>(e => { e.ToView(null); });
    }
}

public class Widget
{
    public int Id { get; set; }
}
