function renderBudgetChart(data, container) {
  const monthNames = ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc'];
  const margin = { top: 20, right: 20, bottom: 40, left: 60 };
  const width = container.offsetWidth - margin.left - margin.right;
  const height = container.offsetHeight - margin.top - margin.bottom;

  // Nettoyer le conteneur
  d3.select(container).selectAll('*').remove();

  const svg = d3.select(container)
    .append('svg')
    .attr('width', width + margin.left + margin.right)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  const months = data.months;
  const groupKeys = ['income', 'expense'];

  const x0 = d3.scaleBand().domain(months).range([0, width]).paddingInner(0.2);
  const x1 = d3.scaleBand().domain(groupKeys).range([0, x0.bandwidth()]).padding(0.05);
  const maxVal = d3.max([...data.income, ...data.expense]) || 100;
  const y = d3.scaleLinear().domain([0, maxVal * 1.1]).range([height, 0]);

  const color = { income: '#2d7a2d', expense: '#a03030' };

  // Axes
  svg.append('g')
    .attr('transform', `translate(0,${height})`)
    .call(d3.axisBottom(x0).tickFormat((d, i) => monthNames[i]));

  svg.append('g')
    .call(d3.axisLeft(y).ticks(5).tickFormat(d => d >= 1000 ? `${d/1000}k` : d));

  // Barres
  const monthGroups = svg.selectAll('.month-group')
    .data(months)
    .join('g')
    .attr('class', 'month-group')
    .attr('transform', d => `translate(${x0(d)},0)`);

  monthGroups.append('rect')
    .attr('x', x1('income'))
    .attr('y', (d, i) => y(data.income[i]))
    .attr('width', x1.bandwidth())
    .attr('height', (d, i) => height - y(data.income[i]))
    .attr('fill', color.income)
    .attr('opacity', 0.85);

  monthGroups.append('rect')
    .attr('x', x1('expense'))
    .attr('y', (d, i) => y(data.expense[i]))
    .attr('width', x1.bandwidth())
    .attr('height', (d, i) => height - y(data.expense[i]))
    .attr('fill', color.expense)
    .attr('opacity', 0.85);

  // Légende
  const legend = svg.append('g').attr('transform', `translate(${width - 120}, 0)`);
  [['income', 'Revenus'], ['expense', 'Dépenses']].forEach(([key, label], i) => {
    legend.append('rect').attr('x', 0).attr('y', i * 18).attr('width', 12).attr('height', 12).attr('fill', color[key]);
    legend.append('text').attr('x', 16).attr('y', i * 18 + 10).text(label).style('font-size', '11px');
  });
}
