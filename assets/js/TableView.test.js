import React from 'react'
import { mount } from 'enzyme'
import { jsonResponseMock } from "./utils";
import TableView from './TableView'
import { mockAddCellEdit, initialRows, deltaRows } from "./TableView";

describe('TableView', () => {

  // Mocks json response (promise) returning part of a larger table
  function makeRenderResponse(start, end, totalRows) {
    let nRows = end-start;
    let data = {
      total_rows: totalRows,
      start_row: start,
      end_row: end,
      columns: ["a", "b", "c"],
      rows: Array(nRows).fill({
        "a": 1,
        "b": 2,
        "c": 3
      })
    };
    return jsonResponseMock(data);
  }

  it('Fetches, renders, and edits cells', (done) => {

    var api = {
      render: makeRenderResponse(0, 2, 1000)
    };

    const tree = mount(<TableView id={100} revision={1} api={api}/>)

    // wait for promise to resolve, then see what we get
    setImmediate(() => {
      // should have called API for its data, and loaded it
      expect(api.render.mock.calls.length).toBe(1);
      expect(api.render.mock.calls[0][0]).toBe(100);
      expect(tree.state().tableData.rows).toHaveLength(2);

      // Header etc should be here
      expect(tree.find('.outputpane-header')).toHaveLength(1);
      expect(tree.find('.outputpane-data')).toHaveLength(1);

      expect(tree).toMatchSnapshot();

      // Row count should have a comma
      let headerText = tree.find('.outputpane-header').text();
      expect(headerText).toContain('1,000');  

      // Test calls to EditCells.addCellEdit
      let addCellEditMock = jest.fn();
      mockAddCellEdit(addCellEditMock);

      // Don't call addCellEdit if the cell value has not changed
      expect(tree.state().tableData.rows[0]['c']).toBe(3);
      tree.instance().onEditCell(0, 'c', '3');            // edited value always string...
      expect(addCellEditMock.mock.calls.length).toBe(0);  // but should still detect no change
      expect(tree.state().tableData.rows[0]['c']).toBe(3);

      // Do call addCellEdit if the cell value has changed
      expect(tree.state().tableData.rows[1]['b']).toBe(2);
      tree.instance().onEditCell(1, 'b', '1000');
      expect(addCellEditMock.mock.calls.length).toBe(1);
      expect(tree.state().tableData.rows[1]['b']).toBe('1000');

      done();
    });
  });


  it('Blank table when no module id', () => {
    const tree = mount(<TableView id={undefined} revision={1} api={{}}/>)
    tree.update();

    expect(tree.find('.outputpane-header')).toHaveLength(1);
    expect(tree.find('.outputpane-data')).toHaveLength(1);
    expect(tree).toMatchSnapshot();
  });

  it('Lazily loads rows as needed', (done) => {

    const totalRows = 100000;

    var api = {
      render: makeRenderResponse(0, initialRows, totalRows) // response to expected first call
    };

    const tree = mount(<TableView id={100} revision={1} api={api}/>);
    let tableView = tree.instance();

    // let rows load
    setImmediate(() => {
      // Should load 0..initialRows at first
      expect(api.render.mock.calls.length).toBe(1);
      expect(api.render.mock.calls[0][0]).toBe(tree.props().id);
      expect(api.render.mock.calls[0][1]).toBe(0);
      expect(api.render.mock.calls[0][2]).toBe(initialRows);

      // if we try to get initialRows + 1, should load to initialRows + 1 + deltaRows
      let requestRow = initialRows + 1;
      let lastLoadedRow = requestRow + deltaRows;
      api.render = makeRenderResponse(initialRows, lastLoadedRow, totalRows);
      let row = tableView.getRow(requestRow);

      // a row we haven't loaded yet should be blank
      expect(row).toEqual(tableView.emptyRow());

      expect(api.render.mock.calls.length).toBe(1);
      expect(api.render.mock.calls[0][1]).toBe(initialRows);
      expect(api.render.mock.calls[0][2]).toBe(lastLoadedRow);

      // let rows load
      setImmediate(() => {

        // Call getRow twice without waiting for the first load to finish, and ensure
        // the next getRow fetches up to the high water mark
        let requestRow2 = lastLoadedRow + 1;
        let lastLoadedRow2 = requestRow2 + deltaRows;
        api.render = makeRenderResponse(lastLoadedRow, lastLoadedRow2, totalRows);
        row = tableView.getRow(requestRow2);
        expect(row).toEqual(tableView.emptyRow());
        expect(api.render.mock.calls.length).toBe(1);
        expect(tableView.loading).toBe(true);

        let requestRow3 = Math.floor(totalRows / 2);  // thousands of rows later
        row = tableView.getRow(requestRow3);
        expect(row).toEqual(tableView.emptyRow());
        expect(api.render.mock.calls.length).toBe(1);   // already loading, should not have started a new load
        expect(api.render.mock.calls[0][1]).toBe(lastLoadedRow);
        expect(api.render.mock.calls[0][2]).toBe(lastLoadedRow2);

        // let rows load
        setImmediate(() => {
          expect(tableView.loading).toBe(false);

          // Now start yet another load, for something much smaller that requestRow3
          let requestRow4 = lastLoadedRow2 + 1;          // ask for very next unloaded row...
          let lastLoadedRow3 = requestRow3 + deltaRows;  // ...but we should end up loading something way later
          tableView.getRow(requestRow4);
          expect(api.render.mock.calls.length).toBe(2);
          expect(api.render.mock.calls[1][1]).toBe(lastLoadedRow2);
          expect(api.render.mock.calls[1][2]).toBe(lastLoadedRow3);

          done();
        })
      })
    })

  })
});


