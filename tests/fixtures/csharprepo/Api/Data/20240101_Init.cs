using Microsoft.EntityFrameworkCore.Migrations;

namespace Acme.Api.Data.Migrations;

public partial class Init : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(
            name: "Audits",
            columns: table => new { Id = table.Column<int>() });
    }
}
