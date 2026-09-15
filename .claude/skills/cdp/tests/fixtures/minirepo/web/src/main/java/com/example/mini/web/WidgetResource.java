package com.example.mini.web;

import com.example.mini.core.Widget;
import com.example.mini.core.WidgetRepository;
import java.util.List;
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;

@Path(ApiPaths.WIDGETS)
public class WidgetResource {

  private final WidgetRepository repository;

  public WidgetResource(WidgetRepository repository) {
    this.repository = repository;
  }

  @GET
  public List<Widget> list() {
    return List.of();
  }

  @GET
  @Path("/{id}")
  public Widget get(@PathParam("id") String id) {
    return new Widget(id);
  }
}
