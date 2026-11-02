@Injectable({ providedIn: 'root' })
export class Svc {
  @Input() name: string;
  @Get(':id')
  find(@Param('id') id: string): string { return id; }
}
